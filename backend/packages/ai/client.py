from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from litellm import completion

from packages.common.settings import AppSettings

API_TIMEOUT = 300


@dataclass(slots=True)
class JsonCallResult:
    parsed: dict[str, Any]
    raw_text: str
    request_id: str | None
    usage: dict[str, int]
    model_name: str


class LLMJsonClient:
    def __init__(self, settings: AppSettings) -> None:
        if not settings.api_key:
            raise ValueError("Missing AI API key.")
        self.settings = settings

    def _candidate_models(self) -> list[str]:
        values = [self.settings.model, *self.settings.fallback_models]
        deduped: list[str] = []
        for value in values:
            if value and value not in deduped:
                deduped.append(value)
        return deduped or [self.settings.model]

    def _to_litellm_model(self, model_name: str) -> str:
        if "/" in model_name:
            return model_name
        if self.settings.provider == "anthropic":
            return f"anthropic/{model_name}"
        return f"openai/{model_name}"

    def _request_kwargs(
        self,
        model_name: str,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int,
        include_reasoning_effort: bool,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self._to_litellm_model(model_name),
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": max_tokens,
            "timeout": API_TIMEOUT,
            "api_key": self.settings.api_key,
        }
        if self.settings.provider == "openai-compatible" and self.settings.base_url:
            kwargs["base_url"] = self.settings.base_url
        if include_reasoning_effort and self.settings.reasoning_effort:
            kwargs["reasoning_effort"] = self.settings.reasoning_effort
        return kwargs

    def _completion(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int,
    ) -> tuple[str, str | None, dict[str, int], str]:
        candidate_models = self._candidate_models()
        response_payload: dict[str, Any] | None = None
        selected_model = candidate_models[0]

        for index, model_name in enumerate(candidate_models, start=1):
            try:
                response = completion(
                    **self._request_kwargs(
                        model_name,
                        messages,
                        max_tokens=max_tokens,
                        include_reasoning_effort=True,
                    )
                )
            except Exception as exc:
                status_code, err_text = self._extract_error_details(exc)
                if (
                    index < len(candidate_models)
                    and self._is_model_unavailable_error(status_code, err_text)
                ):
                    continue

                if self.settings.reasoning_effort and self._is_reasoning_unsupported_error(
                    status_code, err_text
                ):
                    try:
                        response = completion(
                            **self._request_kwargs(
                                model_name,
                                messages,
                                max_tokens=max_tokens,
                                include_reasoning_effort=False,
                            )
                        )
                    except Exception as retry_exc:
                        retry_status, retry_text = self._extract_error_details(retry_exc)
                        if (
                            index < len(candidate_models)
                            and self._is_model_unavailable_error(retry_status, retry_text)
                        ):
                            continue
                        raise RuntimeError(
                            f"AI API call failed ({retry_status or 'error'}): {retry_text}"
                        ) from retry_exc
                else:
                    raise RuntimeError(
                        f"AI API call failed ({status_code or 'error'}): {err_text}"
                    ) from exc

            response_payload = self._response_to_payload(response)
            selected_model = str(response_payload.get("model") or model_name).strip() or model_name
            break

        if response_payload is None:
            raise RuntimeError("AI API call failed: no successful response")

        text = self._extract_text(response_payload)
        if not text:
            raise RuntimeError("AI response returned empty output")

        request_id = str(response_payload.get("id") or "").strip() or None
        usage = self._extract_usage(response_payload)
        return text, request_id, usage, selected_model

    @staticmethod
    def _extract_error_details(exc: Exception) -> tuple[int | None, str]:
        status_code = getattr(exc, "status_code", None)
        response = getattr(exc, "response", None)
        if status_code is None and response is not None:
            status_code = getattr(response, "status_code", None)
        text = str(exc).strip()
        return status_code if isinstance(status_code, int) else None, text[:800] or "unknown error"

    @staticmethod
    def _response_to_payload(response: Any) -> dict[str, Any]:
        if hasattr(response, "model_dump"):
            payload = response.model_dump()
            if isinstance(payload, dict):
                return payload
        if isinstance(response, dict):
            return response
        raise RuntimeError("Unexpected AI response shape")

    @staticmethod
    def _extract_text(payload: dict[str, Any]) -> str:
        choices = payload.get("choices") or []
        if not isinstance(choices, list):
            return ""

        text_parts: list[str] = []
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            message = choice.get("message") or {}
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content
            if isinstance(content, list):
                for item in content:
                    if not isinstance(item, dict):
                        continue
                    if item.get("type") in {"text", "output_text"}:
                        value = str(item.get("text") or "").strip()
                        if value:
                            text_parts.append(value)
        return "".join(text_parts)

    @staticmethod
    def _extract_usage(payload: dict[str, Any]) -> dict[str, int]:
        usage_payload = payload.get("usage") or {}
        if not isinstance(usage_payload, dict):
            return {"input_tokens": 0, "output_tokens": 0}
        return {
            "input_tokens": int(
                usage_payload.get("prompt_tokens")
                or usage_payload.get("input_tokens")
                or 0
            ),
            "output_tokens": int(
                usage_payload.get("completion_tokens")
                or usage_payload.get("output_tokens")
                or 0
            ),
        }

    @staticmethod
    def _is_model_unavailable_error(status_code: int | None, err_text: str) -> bool:
        if status_code is not None and status_code not in {400, 404, 422, 429, 500, 503}:
            return False
        msg = (err_text or "").lower()
        markers = (
            "model_not_found",
            "no available channel for model",
            "model is not found",
            "model does not exist",
            "unsupported model",
            "not supported for",
            "unknown model",
        )
        return any(marker in msg for marker in markers)

    @staticmethod
    def _is_reasoning_unsupported_error(status_code: int | None, err_text: str) -> bool:
        if status_code is not None and status_code not in {400, 422}:
            return False
        return "reasoning_effort" in (err_text or "").lower()

    def generate_json(
        self,
        messages: list[dict[str, Any]],
        *,
        required_keys: list[str],
        max_tokens: int = 4000,
    ) -> JsonCallResult:
        text, request_id, usage, model_name = self._completion(messages, max_tokens=max_tokens)
        try:
            parsed = self._loads_with_fallback(text)
        except Exception:
            repair_messages = messages + [
                {"role": "assistant", "content": text[:12000]},
                {
                    "role": "user",
                    "content": (
                        "The previous response was not valid JSON.\n"
                        "Return ONLY one JSON object with these top-level keys: "
                        + ", ".join(required_keys)
                        + "."
                    ),
                },
            ]
            repaired_text, repaired_request_id, repaired_usage, repaired_model = self._completion(
                repair_messages,
                max_tokens=max_tokens,
            )
            parsed = self._loads_with_fallback(repaired_text)
            text = repaired_text
            request_id = ",".join(
                [value for value in (request_id, repaired_request_id) if value]
            ) or None
            usage = {
                "input_tokens": int(usage.get("input_tokens", 0))
                + int(repaired_usage.get("input_tokens", 0)),
                "output_tokens": int(usage.get("output_tokens", 0))
                + int(repaired_usage.get("output_tokens", 0)),
            }
            model_name = repaired_model

        for key in required_keys:
            parsed.setdefault(key, [] if key.endswith("s") else "")
        return JsonCallResult(
            parsed=parsed,
            raw_text=text,
            request_id=request_id,
            usage=usage,
            model_name=model_name,
        )

    @staticmethod
    def _fix_unescaped_quotes(text: str) -> str:
        result: list[str] = []
        i = 0
        n = len(text)
        while i < n:
            ch = text[i]
            if ch == '"':
                result.append(ch)
                i += 1
                while i < n:
                    c = text[i]
                    if c == "\\":
                        result.append(c)
                        i += 1
                        if i < n:
                            result.append(text[i])
                            i += 1
                        continue
                    if c == '"':
                        j = i + 1
                        while j < n and text[j] in " \t\r\n":
                            j += 1
                        if j >= n or text[j] in ",:}]":
                            result.append(c)
                            i += 1
                            break
                        result.append('\\"')
                        i += 1
                        continue
                    if c == "\n":
                        result.append("\\n")
                        i += 1
                        continue
                    result.append(c)
                    i += 1
            else:
                result.append(ch)
                i += 1
        return "".join(result)

    @staticmethod
    def _fix_invalid_escapes(text: str) -> str:
        valid_escapes = set('"\\bfnrtu/')
        result: list[str] = []
        i = 0
        n = len(text)
        in_str = False
        while i < n:
            ch = text[i]
            if not in_str:
                if ch == '"':
                    in_str = True
                result.append(ch)
                i += 1
                continue
            if ch == "\\":
                if i + 1 < n and text[i + 1] in valid_escapes:
                    result.append(ch)
                    result.append(text[i + 1])
                    i += 2
                    continue
                result.append("\\\\")
                i += 1
                continue
            if ch == '"':
                in_str = False
            result.append(ch)
            i += 1
        return "".join(result)

    @staticmethod
    def _loads_with_fallback(text: str) -> dict[str, Any]:
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass

        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
        if fence:
            obj = json.loads(fence.group(1))
            if isinstance(obj, dict):
                return obj

        start = text.find("{")
        if start < 0:
            raise ValueError("Response is not valid JSON.")
        depth = 0
        in_str = False
        escape = False
        end = -1
        for index in range(start, len(text)):
            ch = text[index]
            if in_str:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = index + 1
                    break
        if end < 0:
            raise ValueError("Response JSON extraction failed.")

        raw = text[start:end]
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

        fixed = LLMJsonClient._fix_unescaped_quotes(raw)
        fixed = LLMJsonClient._fix_invalid_escapes(fixed)
        obj = json.loads(fixed)
        if not isinstance(obj, dict):
            raise ValueError("Response JSON is not an object.")
        return obj
