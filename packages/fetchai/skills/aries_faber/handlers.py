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
"""This package contains the handlers for the faber_alice skill."""
import json
import random
from typing import Any, Dict, List, Optional, cast

from aea.common import Address
from aea.configurations.base import PublicId
from aea.protocols.base import Message
from aea.skills.base import Handler

from packages.fetchai.protocols.default.message import DefaultMessage
from packages.fetchai.protocols.http.message import HttpMessage
from packages.fetchai.protocols.oef_search.message import OefSearchMessage
from packages.fetchai.skills.aries_faber.dialogues import (
    DefaultDialogues,
    HttpDialogue,
    HttpDialogues,
    OefSearchDialogue,
    OefSearchDialogues,
)
from packages.fetchai.skills.aries_faber.strategy import (
    ADMIN_COMMAND_CREATE_INVITATION,
    ADMIN_COMMAND_CREDDEF,
    ADMIN_COMMAND_REGISTGER_PUBLIC_DID,
    ADMIN_COMMAND_SCEHMAS,
    ADMIN_COMMAND_STATUS,
    FABER_ACA_IDENTITY,
    LEDGER_COMMAND_REGISTER_DID,
    Strategy,
)


DEFAULT_SEARCH_INTERVAL = 5.0
SUPPORT_REVOCATION = False


class HttpHandler(Handler):
    """This class represents faber's handler for default messages."""

    SUPPORTED_PROTOCOL = HttpMessage.protocol_id  # type: Optional[PublicId]

    def __init__(self, **kwargs: Any):
        """Initialize the handler."""
        super().__init__(**kwargs)

        # ACA stuff
        self.faber_identity = FABER_ACA_IDENTITY

        self.did = None  # type: Optional[str]
        self._schema_id = None  # type: Optional[str]
        self.credential_definition_id = None  # type: Optional[str]

        # connections
        self.connections_sent: Dict[str, Address] = {}
        self.connections_set: Dict[str, Address] = {}
        self.counterparts_names: Dict[Address, str] = {}

    @property
    def schema_id(self) -> str:
        """Get schema id."""
        if self._schema_id is None:
            raise ValueError("schema_id not set")
        return self._schema_id

    def _send_invitation_message(self, connection: Dict) -> None:
        """
        Send a default message to Alice.

        :param connection: the content of the connection message.
        """
        strategy = cast(Strategy, self.context.strategy)
        # context
        connections_unsent = list(
            set(strategy.aea_addresses) - set(self.connections_sent.values())
        )
        if not connections_unsent:
            self.context.logger.info(
                "Every invitation pushed, skip this new connection"
            )
            return
        target = connections_unsent[0]
        invitation = connection["invitation"]

        self.connections_sent[connection["connection_id"]] = target

        default_dialogues = cast(DefaultDialogues, self.context.default_dialogues)
        message, _ = default_dialogues.create(
            counterparty=target,
            performative=DefaultMessage.Performative.BYTES,
            content=json.dumps(invitation).encode("utf-8"),
        )
        # send
        self.context.outbox.put_message(message=message)

        self.context.logger.info(f"connection: {str(connection)}")
        self.context.logger.info(f"connection id: {connection['connection_id']}")  # type: ignore
        self.context.logger.info(f"invitation: {str(invitation)}")
        self.context.logger.info(
            f"Sent invitation to {target}. Waiting for the invitation from agent {target} to finalise the connection..."
        )

    def _register_public_did_on_acapy(self) -> None:
        """Register DID on the ACA PY."""
        strategy = cast(Strategy, self.context.strategy)
        self.context.behaviours.faber.send_http_request_message(
            method="POST",
            url=strategy.admin_url
            + ADMIN_COMMAND_REGISTGER_PUBLIC_DID
            + f"?did={self.did}",
            content="",
        )

    def _register_did(self) -> None:
        """Register DID on the ledger."""
        strategy = cast(Strategy, self.context.strategy)
        self.context.logger.info(
            f"Registering Faber_ACA with seed {str(strategy.seed)}"
        )
        data = {
            "alias": self.faber_identity,
            "seed": strategy.seed,
            "role": "TRUST_ANCHOR",
        }
        self.context.behaviours.faber.send_http_request_message(
            method="POST",
            url=strategy.ledger_url + LEDGER_COMMAND_REGISTER_DID,
            content=data,
        )

    def _register_schema(
        self, schema_name: str, version: str, schema_attrs: List[str]
    ) -> None:
        """
        Register schema definition.

        :param schema_name: the name of the schema
        :param version: the version of the schema
        :param schema_attrs: the attributes of the schema
        """
        strategy = cast(Strategy, self.context.strategy)
        schema_body = {
            "schema_name": schema_name,
            "schema_version": version,
            "attributes": schema_attrs,
        }
        self.context.logger.info(f"Registering schema {str(schema_body)}")
        # The following call isn't responded to. This is most probably because of missing options when running the accompanying ACA.
        # The accompanying ACA is not properly connected to the von network ledger (missing pointer to genesis file/wallet type)
        self.context.behaviours.faber.send_http_request_message(
            method="POST",
            url=strategy.admin_url + ADMIN_COMMAND_SCEHMAS,
            content=schema_body,
        )

    def _register_creddef(self, schema_id: str) -> None:
        """
        Register credential definition.

        :param schema_id: the id of the schema definition registered on the ledger
        """
        strategy = cast(Strategy, self.context.strategy)
        credential_definition_body = {
            "schema_id": schema_id,
            "support_revocation": SUPPORT_REVOCATION,
        }
        self.context.behaviours.faber.send_http_request_message(
            method="POST",
            url=strategy.admin_url + ADMIN_COMMAND_CREDDEF,
            content=credential_definition_body,
        )

    def setup(self) -> None:
        """Implement the setup."""

    def handle(self, message: Message) -> None:
        """
        Implement the reaction to an envelope.

        :param message: the message
        """
        message = cast(HttpMessage, message)

        # recover dialogue
        http_dialogues = cast(HttpDialogues, self.context.http_dialogues)
        http_dialogue = cast(Optional[HttpDialogue], http_dialogues.update(message))
        if http_dialogue is None:
            self.context.logger.error(
                "something went wrong when adding the incoming HTTP message to the dialogue."
            )
            return

        strategy = cast(Strategy, self.context.strategy)

        if (
            message.performative == HttpMessage.Performative.RESPONSE
            and message.status_code == 200
        ):  # response to http request
            content_bytes = message.body  # type: ignore
            content = json.loads(content_bytes)
            self.context.logger.info(f"Received message: {str(content)}")
            if "version" in content:  # response to /status
                self._register_did()
            elif "did" in content:
                self.did = content["did"]
                self.context.logger.info(f"Received DID: {self.did}")
                self._register_public_did_on_acapy()
            elif "result" in content and "posture" in content["result"]:
                self.context.logger.info(f"Registered public DID: {content}")
                self._register_schema(
                    schema_name="degree schema",
                    version="0.0.1",
                    schema_attrs=["average", "date", "degree", "name"],
                )
            elif "schema_id" in content:
                self._schema_id = content["schema_id"]
                self._register_creddef(self.schema_id)
            elif "credential_definition_id" in content:
                self.credential_definition_id = content["credential_definition_id"]
                for _ in strategy.aea_addresses:
                    # issue invitation for every agent
                    self.context.behaviours.faber.send_http_request_message(
                        method="POST",
                        url=strategy.admin_url + ADMIN_COMMAND_CREATE_INVITATION,
                    )
            elif "invitation" in content:
                connection = content
                self._send_invitation_message(connection)

            elif "credential_proposal_dict" in content:
                connection_id = content["connection_id"]
                addr = self.connections_set[connection_id]
                name = self.counterparts_names[addr]
                self.context.logger.info(
                    f"Credential issued for {name}({addr}): {content['credential_offer_dict']['credential_preview']}"
                )
            else:
                self.context.logger.warning("UNKNOWN HTTP MESSAGE RESPONSE", message)
        elif (
            message.performative == HttpMessage.Performative.REQUEST
        ):  # webhook request
            content_bytes = message.body
            content = json.loads(content_bytes)
            self.context.logger.info(f"Received webhook message content:{str(content)}")
            if "connection_id" in content:
                connection_id = content["connection_id"]
                if connection_id not in self.connections_sent:
                    return
                if not (
                    content["state"] == "active"
                    and connection_id not in self.connections_set
                ):
                    return
                addr = self.connections_sent[connection_id]
                name = content["their_label"]
                self.counterparts_names[addr] = name
                self.connections_set[connection_id] = addr
                self.context.logger.info(f"Connected to {name}({addr})")
                self.issue_crendetials_for(name, addr, connection_id)

    def issue_crendetials_for(
        self, name: str, address: Address, connection_id: str
    ) -> None:
        """Issue credentials for the agent."""
        cred = {
            "connection_id": connection_id,
            "cred_def_id": self.credential_definition_id,
            "credential_proposal": {
                "@type": "did:sov:BzCbsNYhMrjHiqZDTUASHg;spec/issue-credential/1.0/credential-preview",
                "attributes": [
                    {"name": "name", "value": name},
                    {"name": "date", "value": "2022-01-01"},
                    {
                        "name": "degree",
                        "value": random.choice(  # nosec
                            ["Physics", "Chemistry", "Mathematics", "History"]
                        ),
                    },
                    {
                        "name": "average",
                        "value": str(random.choice([3, 4, 5])),  # nosec
                    },
                ],
            },
        }
        strategy = cast(Strategy, self.context.strategy)
        self.context.behaviours.faber.send_http_request_message(
            method="POST",
            url=strategy.admin_url + "/issue-credential/send",
            content=cred,
        )

        self.context.logger.info(
            f"Credentials issue requested for {name}({address}) {cred}"
        )

    def teardown(self) -> None:
        """Implement the handler teardown."""


class OefSearchHandler(Handler):
    """This class implements an OEF search handler."""

    SUPPORTED_PROTOCOL = OefSearchMessage.protocol_id  # type: Optional[PublicId]

    def setup(self) -> None:
        """Call to setup the handler."""

    def handle(self, message: Message) -> None:
        """
        Implement the reaction to a message.

        :param message: the message
        """
        self.context.logger.info("Handling SOEF message...")
        oef_search_msg = cast(OefSearchMessage, message)

        # recover dialogue
        oef_search_dialogues = cast(
            OefSearchDialogues, self.context.oef_search_dialogues
        )
        oef_search_dialogue = cast(
            Optional[OefSearchDialogue], oef_search_dialogues.update(oef_search_msg)
        )
        if oef_search_dialogue is None:
            self._handle_unidentified_dialogue(oef_search_msg)
            return

        # handle message
        if oef_search_msg.performative is OefSearchMessage.Performative.OEF_ERROR:
            self._handle_error(oef_search_msg, oef_search_dialogue)
        elif oef_search_msg.performative is OefSearchMessage.Performative.SEARCH_RESULT:
            self._handle_search(oef_search_msg)
        else:
            self._handle_invalid(oef_search_msg, oef_search_dialogue)

    def teardown(self) -> None:
        """Implement the handler teardown."""

    def _handle_unidentified_dialogue(self, oef_search_msg: OefSearchMessage) -> None:
        """
        Handle an unidentified dialogue.

        :param oef_search_msg: the oef search message to be handled
        """
        self.context.logger.info(
            "received invalid oef_search message={}, unidentified dialogue.".format(
                oef_search_msg
            )
        )

    def _handle_error(
        self, oef_search_msg: OefSearchMessage, oef_search_dialogue: OefSearchDialogue
    ) -> None:
        """
        Handle an oef search message.

        :param oef_search_msg: the oef search message to be handled
        :param oef_search_dialogue: the dialogue
        """
        self.context.logger.info(
            "received oef_search error message={} in dialogue={}.".format(
                oef_search_msg, oef_search_dialogue
            )
        )

    def _handle_search(self, oef_search_msg: OefSearchMessage) -> None:
        """
        Handle the search response.

        :param oef_search_msg: the oef search message to be handled
        """

        if len(oef_search_msg.agents) <= 1:
            self.context.logger.info("Waiting for more agents.")
            return

        self.context.logger.info(
            f"found agents {', '.join(oef_search_msg.agents)}, stopping search."
        )

        strategy = cast(Strategy, self.context.strategy)
        strategy.is_searching = False  # stopping search

        # set alice address
        strategy.aea_addresses = list(oef_search_msg.agents)

        # check ACA is running
        self.context.behaviours.faber.send_http_request_message(
            "GET", strategy.admin_url + ADMIN_COMMAND_STATUS
        )

    def _handle_invalid(
        self, oef_search_msg: OefSearchMessage, oef_search_dialogue: OefSearchDialogue
    ) -> None:
        """
        Handle an oef search message.

        :param oef_search_msg: the oef search message
        :param oef_search_dialogue: the dialogue
        """
        self.context.logger.warning(
            "cannot handle oef_search message of performative={} in dialogue={}.".format(
                oef_search_msg.performative, oef_search_dialogue,
            )
        )
