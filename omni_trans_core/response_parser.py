import re
import logging
from .interfaces import AbstractResponseParser, UsageMetadata
from typing import Any, override


logger = logging.getLogger('CORE.response_parser')

class DefaultResponseParser(AbstractResponseParser):
    @override
    def parse(
        self, response: Any, job_data: dict[str, Any]
    ) -> tuple[str, str, UsageMetadata]:
        return self._parse_litellm(response, job_data)

    def _extract_thinking_from_message(self, message: Any, is_dict: bool) -> str | None:
        if is_dict:
            reasoning = message.get("reasoning_content")
            if reasoning:
                return self._normalize_thinking(reasoning)
            thought = message.get("thought")
            if thought:
                return self._normalize_thinking(thought)
            thinking_blocks = message.get("thinking_blocks")
            if thinking_blocks:
                return self._extract_from_thinking_blocks(thinking_blocks)
            provider_fields = message.get("provider_specific_fields", {})
            if isinstance(provider_fields, dict):
                thinking_blocks = provider_fields.get("thinking_blocks")
                if thinking_blocks:
                    return self._extract_from_thinking_blocks(thinking_blocks)
        else:
            reasoning = getattr(message, "reasoning_content", None)
            if reasoning:
                return self._normalize_thinking(reasoning)
            thought = getattr(message, "thought", None)
            if thought:
                return self._normalize_thinking(thought)
            thinking_blocks = getattr(message, "thinking_blocks", None)
            if thinking_blocks:
                return self._extract_from_thinking_blocks(thinking_blocks)
            provider_fields = getattr(message, "provider_specific_fields", None)
            if provider_fields:
                thinking_blocks = getattr(provider_fields, "thinking_blocks", None)
                if thinking_blocks:
                    return self._extract_from_thinking_blocks(thinking_blocks)
        return None

    @staticmethod
    def _extract_from_thinking_blocks(thinking_blocks: Any) -> str:
        parts = []
        blocks = thinking_blocks if isinstance(thinking_blocks, list) else []
        for block in blocks:
            if isinstance(block, dict):
                thinking_text = block.get("thinking", "")
                if thinking_text:
                    parts.append(thinking_text)
            elif hasattr(block, "thinking"):
                text = getattr(block, "thinking", "")
                if text:
                    parts.append(text)
        if parts:
            return "\n\n---\n\n".join(parts).strip()
        return ""

    def _extract_thinking_from_response(self, response: Any) -> str | None:
        if isinstance(response, dict):
            thinking = response.get("thinking")
        else:
            thinking = getattr(response, "thinking", None)
        if thinking:
            return self._normalize_thinking(thinking)
        return None

    @staticmethod
    def _normalize_thinking(thinking: Any) -> str:
        if isinstance(thinking, list):
            parts = []
            for item in thinking:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text", "")
                    if text:
                        parts.append(str(text))
                else:
                    parts.append(str(item))
            return "\n".join(parts).strip()
        return str(thinking).strip()

    def _parse_litellm(
        self, response: Any, job_data: dict[str, Any]
    ) -> tuple[str, str, UsageMetadata]:
        thinking_text = ""
        final_processed_translation = ""
        usage_metadata: UsageMetadata = {}
        try:
            if isinstance(response, dict):
                choices = response.get("choices", [])
                usage = response.get("usage", {})
            elif hasattr(response, "choices"):
                choices = response.choices
                usage = response.usage
            else:
                raise AttributeError("Unsupported response type")
            
            thinking_from_response = self._extract_thinking_from_response(response)
            if thinking_from_response:
                thinking_text = thinking_from_response
                logger.debug(
                    "Successfully parsed 'thoughts' from response.thinking (top-level)."
                )

            if not choices:
                if thinking_text:
                    logger.debug("Response has no 'choices' but thinking was found at top level.")
                else:
                    raise IndexError("Response has no 'choices'")
            
            if choices:
                choice = choices[0]
                message = (
                    choice.get("message") if isinstance(choice, dict) else choice.message
                )
                raw_content = (
                    message.get("content")
                    if isinstance(message, dict)
                    else getattr(message, "content", "")
                )
                
                if not thinking_text:
                    thinking_from_message = self._extract_thinking_from_message(
                        message, isinstance(message, dict)
                    )
                    if thinking_from_message:
                        thinking_text = thinking_from_message
                        final_processed_translation = raw_content if raw_content else ""
                        logger.debug(
                            "Successfully parsed 'thoughts' from message (reasoning_content/thought)."
                        )

                if not thinking_text:
                    choice_thinking_blocks = (
                        choice.get("thinking_blocks")
                        if isinstance(choice, dict)
                        else getattr(choice, "thinking_blocks", None)
                    )
                    if choice_thinking_blocks:
                        thinking_text = self._extract_from_thinking_blocks(choice_thinking_blocks)
                        if thinking_text:
                            final_processed_translation = raw_content if raw_content else ""
                            logger.debug(
                                "Successfully parsed 'thoughts' from choice.thinking_blocks."
                            )

                if not thinking_text:
                    if isinstance(raw_content, list):
                        logger.debug("Parsing structured (list) content from response.")
                        thinking_parts, translation_parts = [], []
                        for part in raw_content:
                            if part.get("type") == "thinking" and "thinking" in part:
                                thinking_content = part["thinking"]
                                if isinstance(thinking_content, list) and thinking_content:
                                    thinking_parts.append(thinking_content[0].get("text", ""))
                                elif isinstance(thinking_content, str):
                                    thinking_parts.append(thinking_content)
                            elif part.get("type") == "text":
                                translation_parts.append(part.get("text", ""))
                        thinking_text = "".join(thinking_parts).strip()
                        final_processed_translation = "".join(translation_parts).strip()
                    elif isinstance(raw_content, str):
                        logger.debug("Parsing standard (string) content from response.")
                        parsing_rules = job_data.get("parsing_rules", {})
                        start_tag, end_tag = (
                            parsing_rules.get("start_tag"),
                            parsing_rules.get("end_tag"),
                        )
                        if start_tag and end_tag:
                            pattern = f"{re.escape(start_tag)}(.*?){re.escape(end_tag)}"
                            matches = re.findall(pattern, raw_content, re.DOTALL)
                            if matches:
                                thinking_text = "\n\n---\n\n".join(
                                    match.strip() for match in matches
                                )
                                final_processed_translation = re.sub(
                                    pattern, "", raw_content, flags=re.DOTALL
                                ).strip()
                            else:
                                final_processed_translation = raw_content
                        else:
                            thinking_text, final_processed_translation = (
                                self._extract_thinking_from_raw_text(raw_content)
                            )
                
                if not final_processed_translation and isinstance(raw_content, str):
                    final_processed_translation = raw_content
            
            final_processed_translation = final_processed_translation.strip().strip('"')
            
            if usage:
                usage_dict = usage if isinstance(usage, dict) else usage.model_dump()
                usage_metadata["prompt"] = usage_dict.get("prompt_tokens", 0)
                usage_metadata["candidates"] = usage_dict.get("completion_tokens", 0)
                usage_metadata["total"] = usage_dict.get("total_tokens", 0)
                details = usage_dict.get("completion_tokens_details") or {}
                if isinstance(details, dict):
                    reasoning_tokens = details.get("reasoning_tokens")
                else:
                    reasoning_tokens = getattr(details, "reasoning_tokens", None)
                usage_metadata["thoughts"] = (
                    reasoning_tokens
                    or usage_dict.get("thoughts_token_count", 0)
                    or 0
                )
        
        except (AttributeError, IndexError, KeyError) as e:
            logger.error(f"Could not parse LiteLLM response: {e}", exc_info=True)
            return "ERROR: See logs", "", {}
        
        if thinking_text:
            logger.debug(f"Parsed thinking text ({len(thinking_text)} chars)")
        
        return final_processed_translation, thinking_text, usage_metadata

    @staticmethod
    def _extract_thinking_from_raw_text(raw_content: str) -> tuple[str, str]:
        
        thinking_patterns = [
            r'<think>\s*(.*?)\s*</think>',
            r'<\|begin_of_thought\|>\s*(.*?)\s*<\|end_of_thought\|>',
            r'<thinking[^>]*>\s*(.*?)\s*</thinking>',
        ]
        for pattern in thinking_patterns:
            matches = re.findall(pattern, raw_content, re.DOTALL | re.IGNORECASE)
            if matches:
                thinking_text = "\n\n---\n\n".join(m.strip() for m in matches)
                cleaned_content = re.sub(
                    pattern, "", raw_content, flags=re.DOTALL | re.IGNORECASE
                ).strip()
                logger.debug(f"Parsed thinking from pattern: {pattern}")
                return thinking_text, cleaned_content
        return "", raw_content
