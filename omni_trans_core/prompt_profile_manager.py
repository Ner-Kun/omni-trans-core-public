"""
Prompt Profile Manager - manages loading, saving, and listing prompt profiles.
"""
import logging
import os
import shutil
from typing import Optional

from .prompt_profile import PromptProfile, get_default_profile

logger = logging.getLogger('CORE.prompt_profile_manager')


class PromptProfileManager:
    """Manages prompt profile files."""

    def __init__(
        self,
        profiles_dir: Optional[str] = None,
        default_profile: Optional[PromptProfile] = None,
    ):
        """
        Initialize the profile manager.

        Args:
            profiles_dir: Directory to store profiles. If None, uses the
                current app's prompts directory.
            default_profile: Profile supplied by the application. Used when
                the profiles directory has no profiles yet.
        """
        self._profiles_dir = profiles_dir
        self._profiles_cache: dict[str, PromptProfile] = {}
        self._default_profile = default_profile
        self._migrated_global_profiles = False

    @property
    def profiles_dir(self) -> str:
        """Get the profiles directory, creating it if necessary."""
        if self._profiles_dir is None:
            from . import settings
            self._profiles_dir = settings.get_prompts_dir()

        if not os.path.exists(self._profiles_dir):
            os.makedirs(self._profiles_dir, exist_ok=True)
            logger.info(f"Created prompts directory: {self._profiles_dir}")

        self._migrate_global_profiles()
        return self._profiles_dir

    def _migrate_global_profiles(self) -> None:
        """Copy profiles from the old global directory into the app scope once."""
        if self._migrated_global_profiles:
            return
        self._migrated_global_profiles = True

        from . import settings

        global_dir = settings.GLOBAL_PROMPTS_DIR
        if not global_dir or not os.path.isdir(global_dir):
            return
        if os.path.normcase(os.path.abspath(global_dir)) == os.path.normcase(
            os.path.abspath(self._profiles_dir)
        ):
            return
        if any(name.endswith(".md") for name in os.listdir(self._profiles_dir)):
            return

        copied = 0
        for filename in os.listdir(global_dir):
            if not filename.endswith(".md"):
                continue
            shutil.copy2(
                os.path.join(global_dir, filename),
                os.path.join(self._profiles_dir, filename),
            )
            copied += 1
        if copied:
            logger.info(
                "Copied %d prompt profiles from global scope to %s",
                copied,
                self._profiles_dir,
            )
    
    def _get_profile_path(self, profile_name: str) -> str:
        """Get the file path for a profile by name."""
        safe_name = profile_name.lower().replace(' ', '_').replace('/', '_').replace('\\', '_')
        return os.path.join(self.profiles_dir, f"{safe_name}.md")
    
    def load_profiles(self) -> list[PromptProfile]:
        """
        Load all profiles from the profiles directory.
        
        Returns:
            List of loaded profiles.
        """
        self._profiles_cache.clear()
        profiles = []
        
        if not os.path.exists(self.profiles_dir):
            logger.info(f"Profiles directory does not exist, creating: {self.profiles_dir}")
            os.makedirs(self.profiles_dir, exist_ok=True)
            # Create default profile
            default = self.get_default_profile()
            profiles.append(default)
            return profiles
        
        for filename in os.listdir(self.profiles_dir):
            if filename.endswith('.md'):
                file_path = os.path.join(self.profiles_dir, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    profile = PromptProfile.from_markdown(content, file_path)
                    profiles.append(profile)
                    self._profiles_cache[profile.profile_name] = profile
                    logger.debug(f"Loaded profile: {profile.profile_name} from {filename}")
                except Exception as e:
                    logger.error(f"Failed to load profile from {filename}: {e}")
        
        # If no profiles found, create default
        if not profiles:
            logger.info("No profiles found, creating default profile")
            profiles.append(self.get_default_profile())
        
        return profiles
    
    def _save_profile_to_file(self, profile: PromptProfile) -> str:
        """Save a profile to its file."""
        file_path = profile._file_path or self._get_profile_path(profile.profile_name)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(profile.to_markdown())
        
        profile._file_path = file_path
        logger.debug(f"Saved profile to: {file_path}")
        return file_path
    
    def get_profile(self, profile_name: str) -> Optional[PromptProfile]:
        """
        Get a profile by name.
        
        Args:
            profile_name: Name of the profile to retrieve.
            
        Returns:
            The profile if found, None otherwise.
        """
        # Check cache first
        if profile_name in self._profiles_cache:
            return self._profiles_cache[profile_name]
        
        # Try to load from disk
        file_path = self._get_profile_path(profile_name)
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                profile = PromptProfile.from_markdown(content, file_path)
                self._profiles_cache[profile_name] = profile
                return profile
            except Exception as e:
                logger.error(f"Failed to load profile {profile_name}: {e}")
        
        return None
    
    def get_default_profile(self) -> PromptProfile:
        """Get or create the default profile."""
        if self._default_profile is None:
            self._default_profile = get_default_profile()

        existing = self.get_profile(self._default_profile.profile_name)
        if existing is not None:
            return existing

        self._save_profile_to_file(self._default_profile)
        self._profiles_cache[self._default_profile.profile_name] = self._default_profile
        return self._default_profile
    
    def save_profile(self, profile: PromptProfile) -> bool:
        """
        Save a profile.
        
        Args:
            profile: The profile to save.
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            self._save_profile_to_file(profile)
            self._profiles_cache[profile.profile_name] = profile
            logger.info(f"Profile saved: {profile.profile_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to save profile {profile.profile_name}: {e}")
            return False
    
    def delete_profile(self, profile_name: str) -> bool:
        """
        Delete a profile.
        
        Args:
            profile_name: Name of the profile to delete.
            
        Returns:
            True if successful, False otherwise.
        """
        profile = self.get_profile(profile_name)
        if profile is None:
            logger.warning(f"Profile not found for deletion: {profile_name}")
            return False
        
        # Don't allow deleting the default profile
        if profile_name == self.get_default_profile().profile_name:
            logger.warning("Cannot delete the default profile")
            return False
        
        try:
            file_path = profile.file_path
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
            
            if profile_name in self._profiles_cache:
                del self._profiles_cache[profile_name]
            
            logger.info(f"Profile deleted: {profile_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete profile {profile_name}: {e}")
            return False
    
    def create_profile(self, profile_name: str, description: str = "") -> PromptProfile:
        """
        Create a new profile.

        Args:
            profile_name: Name for the new profile.
            description: Optional description.

        Returns:
            The newly created profile.
        """
        # Check if name already exists
        if self.get_profile(profile_name):
            raise ValueError(f"Profile with name '{profile_name}' already exists")

        # Create new profile based on the current default
        new_profile = self.get_default_profile().copy()
        new_profile.profile_name = profile_name
        new_profile.profile_description = description
        new_profile._file_path = None  # Will be set on save

        # Add to cache so get_profile can find it
        self._profiles_cache[profile_name] = new_profile
        logger.debug(f"Created new profile '{profile_name}' and added to cache")

        return new_profile
    
    def duplicate_profile(self, source_name: str, new_name: str) -> Optional[PromptProfile]:
        """
        Duplicate an existing profile with a new name.
        
        Args:
            source_name: Name of the profile to duplicate.
            new_name: Name for the new profile.
            
        Returns:
            The new profile if successful, None otherwise.
        """
        source = self.get_profile(source_name)
        if source is None:
            logger.error(f"Source profile not found: {source_name}")
            return None
        
        if self.get_profile(new_name):
            logger.error(f"Profile with name '{new_name}' already exists")
            return None
        
        new_profile = source.copy()
        new_profile.profile_name = new_name
        new_profile._file_path = None
        
        return new_profile
    
    def list_profiles(self) -> list[str]:
        """
        Get a list of all profile names.
        
        Returns:
            List of profile names.
        """
        if not self._profiles_cache:
            self.load_profiles()
        
        return list(self._profiles_cache.keys())
    
    def profile_exists(self, profile_name: str) -> bool:
        """Check if a profile exists."""
        return self.get_profile(profile_name) is not None
    
    def rename_profile(self, old_name: str, new_name: str) -> bool:
        """
        Rename a profile.
        
        Args:
            old_name: Current name of the profile.
            new_name: New name for the profile.
            
        Returns:
            True if successful, False otherwise.
        """
        profile = self.get_profile(old_name)
        if profile is None:
            logger.error(f"Profile not found: {old_name}")
            return False
        
        if self.get_profile(new_name):
            logger.error(f"Profile with name '{new_name}' already exists")
            return False
        
        # Remove old file
        old_path = profile.file_path
        if old_path and os.path.exists(old_path):
            os.remove(old_path)
        
        # Update and save with new name
        profile.profile_name = new_name
        profile._file_path = None
        self.save_profile(profile)
        
        # Update cache
        if old_name in self._profiles_cache:
            del self._profiles_cache[old_name]
        self._profiles_cache[new_name] = profile
        
        return True
    
    def get_profile_path(self, profile_name: str) -> str:
        """Get the file path for a profile."""
        return self._get_profile_path(profile_name)