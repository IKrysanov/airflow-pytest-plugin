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

"""Safe report-assistant errors and their HTTP status contracts."""


class AssistantError(Exception):
    """A safe, expected assistant error suitable for an HTTP response."""

    status_code = 502


class AssistantDisabledError(AssistantError):
    """The assistant is not configured on this API server."""

    status_code = 503


class AssistantBusyError(AssistantError):
    """All bounded assistant slots are occupied."""

    status_code = 429


class AssistantRequestError(AssistantError):
    """The caller supplied an invalid question or scope."""

    status_code = 400


class AssistantForbiddenError(AssistantError):
    """The caller explicitly scoped the question to a forbidden DAG."""

    status_code = 403


class AssistantProviderError(AssistantError):
    """A local or remote model could not produce an answer."""

    status_code = 502


__all__ = [
    "AssistantBusyError",
    "AssistantDisabledError",
    "AssistantError",
    "AssistantForbiddenError",
    "AssistantProviderError",
    "AssistantRequestError",
]
