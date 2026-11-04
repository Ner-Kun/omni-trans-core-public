import logging
from typing import override
from .interfaces import AbstractPromptFormatter, TranslatableItem

logger = logging.getLogger('CORE.prompt_formatter')


def _safe_format(template: str, replacements: dict[str, str]) -> str:
    result = template
    for key, value in replacements.items():
        result = result.replace(f"{{{key}}}", str(value) if value is not None else "")
    return result


class DefaultPromptFormatter(AbstractPromptFormatter):
    def __init__(
        self,
        system_prompt: str,
        user_prompt: str,
        regen_prompt: str,
        context_instructions: str = "",
    ):
        self.system_prompt_template: str = system_prompt
        self.user_prompt_template: str = user_prompt
        self.regen_prompt_template: str = regen_prompt
        self.context_instructions_template: str = context_instructions
        logger.debug("DefaultPromptFormatter initialized with custom templates.")

    def update_templates(
        self,
        system_prompt: str,
        user_prompt: str,
        regen_prompt: str,
        context_instructions: str = "",
    ):
        """Update prompt templates at runtime."""
        self.system_prompt_template = system_prompt
        self.user_prompt_template = user_prompt
        self.regen_prompt_template = regen_prompt
        self.context_instructions_template = context_instructions
        logger.debug("Prompt templates updated.")

    @override
    def format_prompt(
        self,
        item: TranslatableItem,
        src_lang: str,
        tgt_lang: str,
        custom_settings: dict[str, str],
        is_regeneration: bool = False,
    ) -> list[dict[str, str]]:
        source_text = item.get("source_text")
        if source_text is None or not str(source_text).strip():
            item_id = item.get("id", "unknown")
            logger.warning(f"None source_text for item '{item_id}'. Using empty string.")
            source_text = ""
        else:
            source_text = str(source_text)

        system_template = self.system_prompt_template
        context_template = self.context_instructions_template
        context_content_for_api = None
        use_context = custom_settings.get("use_content_as_context", True)
        if use_context and item.get("context") and str(item["context"]).strip():
            context_content_for_api = str(item["context"]).strip()
        
        context_instructions_block = ""
        if context_content_for_api and context_template.strip():
            context_instructions_block = _safe_format(
                context_template, {"context_section": context_content_for_api}
            )
        
        final_system_prompt = _safe_format(
            system_template,
            {
                "context_instructions": context_instructions_block,
                "source_language_name": src_lang,
                "target_language_name": tgt_lang,
            },
        )
        
        if is_regeneration:
            user_template = self.regen_prompt_template
            wrong_keyword = item.get("existing_translation") or ""
            if wrong_keyword is None:
                wrong_keyword = ""
                logger.debug(f"existing_translation is None for item '{item.get('id', 'unknown')}'")
            formatted_user_prompt = _safe_format(
                user_template,
                {
                    "source_language_name": src_lang,
                    "target_language_name": tgt_lang,
                    "keyword": source_text,
                    "wrong_keyword": wrong_keyword,
                },
            )
        else:
            user_template = self.user_prompt_template
            formatted_user_prompt = _safe_format(
                user_template,
                {
                    "source_language_name": src_lang,
                    "target_language_name": tgt_lang,
                    "keyword": source_text,
                },
            )
        
        messages = [
            {"role": "system", "content": final_system_prompt},
            {"role": "user", "content": formatted_user_prompt},
        ]
        return messages