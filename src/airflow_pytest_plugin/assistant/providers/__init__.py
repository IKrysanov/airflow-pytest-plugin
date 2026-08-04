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

"""Final-answer providers, one module per SDK.

Each adapter owns exactly one vendor's client and imports that SDK lazily inside its own
constructor, so installing one provider extra never drags in another's dependency and the
package stays importable on a worker that has none of them.

They all satisfy :class:`~airflow_pytest_plugin.assistant.common.AnswerProvider`; the three
network ones additionally implement ``stream``. The context *reducers* deliberately live
outside this package -- ``llama`` and ``passthrough`` compact evidence before it leaves the
server and never write an answer.
"""

from __future__ import annotations

from .anthropic import AnthropicAssistant
from .fake import FakeAnswerProvider, FakeAssistant
from .gigachat import GigaChatAssistant
from .openai import OpenAIAssistant

__all__ = [
    "AnthropicAssistant",
    "FakeAnswerProvider",
    "FakeAssistant",
    "GigaChatAssistant",
    "OpenAIAssistant",
]
