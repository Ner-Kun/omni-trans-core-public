"""Dialog widgets for the core UI.

Split out of the former ``omni_trans_core/ui/dialogs.py`` module; re-exports the
same public names so existing ``from omni_trans_core.ui.dialogs import X``
imports keep working.
"""

from .additional_params import AdditionalParametersDialog
from .connections import ConnectionsDialog
from .donation import DonationDialog
from .languages import ManageLanguagesDialog
from .model_inspector import ModelInspectorDialog
from .progress import ProgressDialog
from .provider_config import (
    PROVIDER_MODEL_HEADER_KEYS,
    PROVIDER_THINKING_MODE_KEYS,
    ProviderConfigAsyncHandler,
    ProviderConfigDialog,
)
from .proxy import ProxyDialog, ProxyTabWidget

__all__ = [
    "AdditionalParametersDialog",
    "ConnectionsDialog",
    "DonationDialog",
    "ManageLanguagesDialog",
    "ModelInspectorDialog",
    "ProgressDialog",
    "ProviderConfigAsyncHandler",
    "ProviderConfigDialog",
    "ProxyDialog",
    "ProxyTabWidget",
    "PROVIDER_MODEL_HEADER_KEYS",
    "PROVIDER_THINKING_MODE_KEYS",
]
