"""
Prompt Profile - data class for storing prompt templates.
Supports Markdown format with YAML frontmatter.
"""
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import yaml

logger = logging.getLogger('CORE.prompt_profile')

# Placeholder patterns
PLACEHOLDER_PATTERN = re.compile(r'\{(\w+)\}')

# Default placeholders
DEFAULT_PLACEHOLDERS = [
    ('{source_language_name}', 'Source language name'),
    ('{target_language_name}', 'Target language name'),
    ('{keyword}', 'Keyword to translate'),
    ('{wrong_keyword}', 'Incorrect translation (for regeneration)'),
    ('{context_instructions}', 'Context instructions block'),
    ('{context_section}', 'Context content'),
]

# Required placeholders for each prompt type
REQUIRED_PLACEHOLDERS = {
    'system_prompt': ['{source_language_name}', '{target_language_name}'],
    'user_prompt': ['{source_language_name}', '{target_language_name}', '{keyword}'],
    'regen_prompt': ['{source_language_name}', '{target_language_name}', '{keyword}', '{wrong_keyword}'],
    'context_instructions': [],
}


@dataclass
class PromptProfile:
    """Data class representing a prompt profile."""
    
    profile_name: str = "Default"
    profile_description: str = ""
    version: str = "1.0"
    created_at: str = ""
    system_prompt: str = ""
    user_prompt: str = ""
    regen_prompt: str = ""
    context_instructions: str = ""
    
    # Internal state
    _file_path: Optional[str] = field(default=None, repr=False)
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().strftime("%Y-%m-%d")
    
    def to_dict(self) -> dict:
        """Convert profile to dictionary."""
        return {
            'profile_name': self.profile_name,
            'profile_description': self.profile_description,
            'version': self.version,
            'created_at': self.created_at,
            'system_prompt': self.system_prompt,
            'user_prompt': self.user_prompt,
            'regen_prompt': self.regen_prompt,
            'context_instructions': self.context_instructions,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'PromptProfile':
        """Create profile from dictionary."""
        return cls(
            profile_name=data.get('profile_name', 'Default'),
            profile_description=data.get('profile_description', ''),
            version=data.get('version', '1.0'),
            created_at=data.get('created_at', ''),
            system_prompt=data.get('system_prompt', ''),
            user_prompt=data.get('user_prompt', ''),
            regen_prompt=data.get('regen_prompt', ''),
            context_instructions=data.get('context_instructions', ''),
        )
    
    def to_markdown(self) -> str:
        """Convert profile to Markdown format with YAML frontmatter."""
        frontmatter = {
            'profile_name': self.profile_name,
            'profile_description': self.profile_description,
            'version': self.version,
            'created_at': self.created_at,
        }
        
        frontmatter_yaml = yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True)
        
        markdown = f"""---
{frontmatter_yaml}---

# System Prompt

{self.system_prompt}

# User Prompt

{self.user_prompt}

# Regen Prompt

{self.regen_prompt}

# Context Instructions

{self.context_instructions}
"""
        return markdown.strip()
    
    @classmethod
    def from_markdown(cls, markdown_content: str, file_path: Optional[str] = None) -> 'PromptProfile':
        """Parse profile from Markdown format with YAML frontmatter."""
        # Split frontmatter and content
        parts = markdown_content.split('---', 2)
        
        if len(parts) < 3:
            logger.warning("No frontmatter found, using defaults")
            frontmatter = {}
            content = markdown_content
        else:
            try:
                frontmatter = yaml.safe_load(parts[1]) or {}
            except yaml.YAMLError as e:
                logger.error(f"Failed to parse YAML frontmatter: {e}")
                frontmatter = {}
            content = parts[2]
        
        # Parse sections
        sections = cls._parse_sections(content)
        
        return cls(
            profile_name=frontmatter.get('profile_name', 'Default'),
            profile_description=frontmatter.get('profile_description', ''),
            version=str(frontmatter.get('version', '1.0')),
            created_at=frontmatter.get('created_at', ''),
            system_prompt=sections.get('system_prompt', ''),
            user_prompt=sections.get('user_prompt', ''),
            regen_prompt=sections.get('regen_prompt', ''),
            context_instructions=sections.get('context_instructions', ''),
            _file_path=file_path,
        )
    
    @staticmethod
    def _parse_sections(content: str) -> dict[str, str]:
        """Parse Markdown content into sections."""
        sections = {}
        
        # Section headers pattern: # Section Name
        section_pattern = re.compile(r'^#\s+(.+?)\s*$', re.MULTILINE)
        
        matches = list(section_pattern.finditer(content))
        
        for i, match in enumerate(matches):
            section_name = match.group(1).lower().replace(' ', '_')
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            section_content = content[start:end].strip()
            sections[section_name] = section_content
        
        return sections
    
    @property
    def file_path(self) -> Optional[str]:
        """Get the file path associated with this profile."""
        return self._file_path
    
    @property
    def file_name(self) -> str:
        """Get the file name (without path) for this profile."""
        if self._file_path:
            return os.path.basename(self._file_path)
        return f"{self.profile_name.lower().replace(' ', '_')}.md"
    
    def get_placeholders(self) -> list[tuple[str, str]]:
        """Get all placeholders used in this profile."""
        placeholders = set()
        
        for attr in ['system_prompt', 'user_prompt', 'regen_prompt', 'context_instructions']:
            text = getattr(self, attr, '')
            found = PLACEHOLDER_PATTERN.findall(text)
            placeholders.update(f'{{{p}}}' for p in found)
        
        return [(p, desc) for p, desc in DEFAULT_PLACEHOLDERS if p in placeholders]
    
    def get_missing_placeholders(self, prompt_type: str) -> list[str]:
        """Get list of missing required placeholders for a prompt type."""
        if prompt_type not in REQUIRED_PLACEHOLDERS:
            return []
        
        text = getattr(self, prompt_type, '')
        found = set(PLACEHOLDER_PATTERN.findall(text))
        found_formatted = {f'{{{p}}}' for p in found}
        
        required = REQUIRED_PLACEHOLDERS[prompt_type]
        return [p for p in required if p not in found_formatted]
    
    def validate(self) -> dict[str, list[str]]:
        """Validate all prompts and return missing placeholders."""
        results = {}
        for prompt_type in REQUIRED_PLACEHOLDERS:
            missing = self.get_missing_placeholders(prompt_type)
            if missing:
                results[prompt_type] = missing
        return results
    
    def is_valid(self) -> bool:
        """Check if profile has all required placeholders."""
        return len(self.validate()) == 0
    
    def copy(self) -> 'PromptProfile':
        """Create a deep copy of this profile."""
        return PromptProfile(
            profile_name=self.profile_name,
            profile_description=self.profile_description,
            version=self.version,
            created_at=self.created_at,
            system_prompt=self.system_prompt,
            user_prompt=self.user_prompt,
            regen_prompt=self.regen_prompt,
            context_instructions=self.context_instructions,
            _file_path=None,  # New copy has no file path
        )


def get_default_profile() -> PromptProfile:
    """Get the default lorebook profile."""
    return PromptProfile(
        profile_name="Lorebook Default",
        profile_description="Default prompt for lorebook translation",
        version="1.0",
        created_at=datetime.now().strftime("%Y-%m-%d"),
        system_prompt="""You are a master linguist and loremaster specializing in localization of lore—whether from games, books, histories or invented universes.
Your mission is to translate LORE keywords from {source_language_name} into {target_language_name}.

1. Output must be concise, accurate — only the translated term.
2. Proper nouns (places, names, items, technologies, mythic concepts):
   • If there's an official or accepted translation in this canon or community, use it.
   • Otherwise, provide a natural‑sounding transliteration when appropriate.

{context_instructions}

STRICTLY no extra text, quotation marks, or explanation—deliver only the final translation.""",
        user_prompt="""{source_language_name} keyword: "{keyword}"
{target_language_name} translation:""",
        regen_prompt="""The {source_language_name} keyword is "{keyword}".
The previous translation attempt was "{wrong_keyword}", which is incorrect or unsatisfactory.
Provide a better, alternative translation into {target_language_name}.
New {target_language_name} translation:""",
        context_instructions="""Use the <context> section to capture genre, usage, significance:
<context>
{context_section}
</context>

Detailed context helps you determine:
– If this is a mythic creature, a historical event, a slang term, a poetic concept?
– Should you invent a neologism fitting genre conventions?
– Or prefer a literal translation for clarity?""",
    )