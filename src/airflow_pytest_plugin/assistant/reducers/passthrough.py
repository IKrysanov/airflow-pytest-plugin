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

"""Deterministic context path used when no local reducer is configured."""

from __future__ import annotations


class PassthroughReducer:
    """Forward the already bounded evidence without another model pass."""

    @property
    def name(self) -> None:
        return None

    def reduce(self, *, question: str, context: str) -> str:
        del question
        return context

    def close(self) -> None:
        return None


__all__ = ["PassthroughReducer"]
