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

"""Offline final-answer adapter for demos and integration tests."""

from __future__ import annotations


class FakeAssistant:
    """Return a deterministic answer without loading or calling a model."""

    @property
    def name(self) -> str:
        return "fake"

    @property
    def model(self) -> str:
        return "offline-fake"

    def answer(self, *, system: str, prompt: str, max_tokens: int) -> str:
        del system, max_tokens
        first = "[R1]" if "[R1]" in prompt else ""
        return (
            "Offline assistant rehearsal completed. "
            f"The configured evidence was received {first}."
        ).strip()

    def close(self) -> None:
        return None


# Backwards-compatible public name used by existing integrations and tests.
FakeAnswerProvider = FakeAssistant

__all__ = ["FakeAnswerProvider", "FakeAssistant"]
