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

"""Context reducers: they compact report evidence, they never answer the user.

A reducer sits between the report tree and the final provider. It satisfies
:class:`~airflow_pytest_plugin.assistant.common.ContextReducer`, and the split from
``providers/`` is the difference in role, not in vendor: a provider writes the answer a
person reads, a reducer only decides which facts are worth sending.

* :mod:`.passthrough` -- the deterministic default. Forwards the already bounded direct
  snapshot unchanged, so no model runs in-process at all.
* :mod:`.llama` -- an optional in-process GGUF, loaded through ``llama-cpp-python``. Its
  prompt deliberately extracts rather than summarizes; see the module for why, and
  ``scripts/grade_reducer.py`` for how a candidate model is graded before it is trusted.

``llama_cpp`` is imported lazily inside the reducer's constructor, so importing this package
costs nothing on a deployment that never configured a local model.
"""

from __future__ import annotations

from .llama import LOCAL_REDUCER_SYSTEM_PROMPT, LlamaCppReducer, safe_local_input_bytes
from .passthrough import PassthroughReducer

__all__ = [
    "LOCAL_REDUCER_SYSTEM_PROMPT",
    "LlamaCppReducer",
    "PassthroughReducer",
    "safe_local_input_bytes",
]
