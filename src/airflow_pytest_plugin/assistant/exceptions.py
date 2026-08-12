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
    """A safe, expected assistant error suitable for an HTTP response.

    Carries two messages on purpose. ``str(error)`` is for the log and the audit record
    and may hold whatever helps somebody debug; :attr:`public_detail` is what may be
    shown to whoever asked. They are the same string for almost every error here, because
    these are written as whole sentences for a reader -- the exception is a failure
    wrapped from a provider SDK, whose own text is written for the account holder and
    carries request ids, endpoint URLs and organisation names.

    Keeping the public half a plain attribute, set where the error is raised, is also
    what stops it being derived from the exception at the point it is written to a
    response: the decision about what is publishable belongs where the error is made.
    """

    status_code = 502

    def __init__(self, message: str = "", *, public: str | None = None) -> None:
        super().__init__(message)
        self.public_detail = public if public is not None else message


class AssistantDisabledError(AssistantError):
    """The assistant is not configured on this API server."""

    status_code = 503


class AssistantBusyError(AssistantError):
    """All bounded assistant slots are occupied."""

    status_code = 429


class AssistantQuotaError(AssistantError):
    """The caller exhausted their request rate or daily token budget."""

    status_code = 429

    def __init__(
        self, message: str, *, retry_after: int = 0, public: str | None = None
    ) -> None:
        super().__init__(message, public=public)
        self.retry_after = retry_after


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
    "AssistantQuotaError",
    "AssistantRequestError",
]
