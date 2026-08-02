# Copyright 2026 the airflow-pytest-plugin contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Public surface for the read-only report-assistant package."""

from .common import (
    MAX_CAPTURE_BYTES,
    MAX_HISTORY_BYTES,
    MAX_HISTORY_CHARS,
    MAX_HISTORY_MESSAGES,
    MAX_QUESTION_CHARS,
    MAX_SCOPE_CHARS,
    MAX_SCOPE_REPORTS,
    AnswerProvider,
    AssistantContext,
    AssistantEvidence,
    AssistantPromptBytes,
    AssistantProviderResponse,
    AssistantQuery,
    AssistantReply,
    AssistantReportContext,
    AssistantScope,
    AssistantTokenUsage,
    AssistantTurn,
    ContextReducer,
)
from .context import ReportContextBuilder
from .exceptions import (
    AssistantBusyError,
    AssistantDisabledError,
    AssistantError,
    AssistantForbiddenError,
    AssistantProviderError,
    AssistantRequestError,
)
from .factory import configured_assistant_runtime
from .fake import FakeAnswerProvider, FakeAssistant
from .passthrough import PassthroughReducer
from .runtime import AssistantRuntime
from .settings import (
    CAPTURE_BYTES_ENV,
    CONTEXT_BYTES_ENV,
    CONTEXT_MAX_TOKENS_ENV,
    CONTEXT_MODEL_ENV,
    CONTEXT_N_CTX_ENV,
    DIRECT_MAX_SUMMARIES_ENV,
    MAX_CONCURRENT_ENV,
    MAX_OUTPUT_TOKENS_ENV,
    MODEL_ENV,
    PROVIDER_ENV,
    TIMEOUT_ENV,
    TRACEBACK_BYTES_ENV,
    AssistantSettings,
)

__all__ = [
    "CAPTURE_BYTES_ENV",
    "CONTEXT_BYTES_ENV",
    "CONTEXT_MAX_TOKENS_ENV",
    "CONTEXT_MODEL_ENV",
    "CONTEXT_N_CTX_ENV",
    "DIRECT_MAX_SUMMARIES_ENV",
    "MAX_CONCURRENT_ENV",
    "MAX_CAPTURE_BYTES",
    "MAX_HISTORY_BYTES",
    "MAX_HISTORY_CHARS",
    "MAX_HISTORY_MESSAGES",
    "MAX_OUTPUT_TOKENS_ENV",
    "MAX_QUESTION_CHARS",
    "MAX_SCOPE_CHARS",
    "MAX_SCOPE_REPORTS",
    "MODEL_ENV",
    "PROVIDER_ENV",
    "TIMEOUT_ENV",
    "TRACEBACK_BYTES_ENV",
    "AnswerProvider",
    "AssistantBusyError",
    "AssistantContext",
    "AssistantDisabledError",
    "AssistantError",
    "AssistantEvidence",
    "AssistantProviderResponse",
    "AssistantPromptBytes",
    "AssistantForbiddenError",
    "AssistantProviderError",
    "AssistantQuery",
    "AssistantReportContext",
    "AssistantReply",
    "AssistantRequestError",
    "AssistantRuntime",
    "AssistantScope",
    "AssistantSettings",
    "AssistantTurn",
    "AssistantTokenUsage",
    "ContextReducer",
    "FakeAnswerProvider",
    "FakeAssistant",
    "PassthroughReducer",
    "ReportContextBuilder",
    "configured_assistant_runtime",
]
