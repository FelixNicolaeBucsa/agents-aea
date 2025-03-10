# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2018-2022 Fetch.AI Limited
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#
# ------------------------------------------------------------------------------
"""This module contains the abstract error handler class."""
from abc import ABC, abstractmethod
from logging import Logger
from typing import Any, Dict

from aea.mail.base import Envelope


class AbstractErrorHandler(ABC):
    """Error handler class for handling problematic envelopes."""

    __slots__ = ("_config",)

    def __init__(self, **kwargs: Any):
        """Instantiate error handler."""
        self._config = kwargs

    @property
    def config(self) -> Dict[str, Any]:
        """Get handler config."""
        return self._config

    @abstractmethod
    def send_unsupported_protocol(self, envelope: Envelope, logger: Logger) -> None:
        """
        Handle the received envelope in case the protocol is not supported.

        :param envelope: the envelope
        :param logger: the logger
        :return: None
        """

    @abstractmethod
    def send_decoding_error(
        self, envelope: Envelope, exception: Exception, logger: Logger
    ) -> None:
        """
        Handle a decoding error.

        :param envelope: the envelope
        :param exception: the exception raised during decoding
        :param logger: the logger
        :return: None
        """

    @abstractmethod
    def send_no_active_handler(
        self, envelope: Envelope, reason: str, logger: Logger
    ) -> None:
        """
        Handle the received envelope in case the handler is not supported.

        :param envelope: the envelope
        :param reason: the reason for the failure
        :param logger: the logger
        :return: None
        """
