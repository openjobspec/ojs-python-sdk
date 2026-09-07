"""Protobuf request/response codec for OJS gRPC calls."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from google.protobuf import json_format
from google.protobuf.descriptor import FieldDescriptor
from google.protobuf.message import DecodeError, Message

from ojs.transport.grpc.descriptor_registry import DescriptorRegistry


class ProtobufCodecError(ValueError):
    """A request or response could not be represented by the OJS protobuf."""


class ProtobufCodec:
    """Encode dictionaries with generated OJS protobuf message descriptors."""

    def __init__(self, registry: DescriptorRegistry | None = None) -> None:
        self._registry = registry or DescriptorRegistry()

    def request_message(self, method: str, data: Mapping[str, Any]) -> Message:
        descriptor = self._registry.method(method)
        try:
            return json_format.ParseDict(dict(data), descriptor.request_type())
        except (json_format.ParseError, TypeError, ValueError) as exc:
            raise ProtobufCodecError(
                f"Invalid {method} request for the OJS protobuf schema: {exc}"
            ) from exc

    def encode_request(self, method: str, data: Mapping[str, Any]) -> bytes:
        return self.request_message(method, data).SerializeToString()

    def decode_response(self, method: str, data: bytes) -> dict[str, Any]:
        descriptor = self._registry.method(method)
        message = descriptor.response_type()
        try:
            message.ParseFromString(data)
        except DecodeError as exc:
            raise ProtobufCodecError(f"Invalid {method} protobuf response: {exc}") from exc
        return self.response_dict(message)

    @staticmethod
    def response_dict(message: Message) -> dict[str, Any]:
        result = json_format.MessageToDict(
            message,
            preserving_proto_field_name=True,
        )
        if not isinstance(result, dict):
            raise ProtobufCodecError("Expected protobuf response to decode to an object")
        _normalize_integer_fields(message, result)
        return result


_INTEGER_FIELD_TYPES = frozenset(
    {
        FieldDescriptor.TYPE_INT32,
        FieldDescriptor.TYPE_INT64,
        FieldDescriptor.TYPE_SINT32,
        FieldDescriptor.TYPE_SINT64,
        FieldDescriptor.TYPE_UINT32,
        FieldDescriptor.TYPE_UINT64,
        FieldDescriptor.TYPE_FIXED32,
        FieldDescriptor.TYPE_FIXED64,
        FieldDescriptor.TYPE_SFIXED32,
        FieldDescriptor.TYPE_SFIXED64,
    }
)


def _normalize_integer_fields(message: Message, data: dict[str, Any]) -> None:
    """Restore native integers lost by protobuf's canonical JSON mapping."""
    for field in message.DESCRIPTOR.fields:
        value = data.get(field.name)
        if value is None:
            continue
        if field.message_type is not None and field.message_type.GetOptions().map_entry:
            if not isinstance(value, dict):
                continue
            value_field = field.message_type.fields_by_name["value"]
            if value_field.type in _INTEGER_FIELD_TYPES:
                for key, item in value.items():
                    value[key] = int(item)
            continue
        if field.is_repeated:
            if field.message_type is not None and isinstance(value, list):
                repeated = getattr(message, field.name)
                for nested_message, nested_data in zip(repeated, value, strict=False):
                    if isinstance(nested_data, dict):
                        _normalize_integer_fields(nested_message, nested_data)
            elif field.type in _INTEGER_FIELD_TYPES and isinstance(value, list):
                data[field.name] = [int(item) for item in value]
            continue
        if field.message_type is not None and isinstance(value, dict):
            _normalize_integer_fields(getattr(message, field.name), value)
        elif field.type in _INTEGER_FIELD_TYPES:
            data[field.name] = int(value)


__all__ = ["ProtobufCodec", "ProtobufCodecError"]
