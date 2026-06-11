"""Typed errors for the Hermes Docker runtime plugin."""


class DockerRuntimeError(Exception):
    """Base class for plugin errors."""


class WorkspacePolicyError(DockerRuntimeError):
    """Raised when a host workspace path is not allowed."""


class ProjectConfigError(DockerRuntimeError):
    """Raised when `.hermes/docker-runtime.json` is invalid."""


class StateStoreError(DockerRuntimeError):
    """Raised when local state cannot be read or written."""


class ContainerValidationError(DockerRuntimeError):
    """Raised when Docker labels or mounts do not match the project binding."""


class WorkspaceNotSet(DockerRuntimeError):
    """Raised when the current session has no workspace alias."""


class ProtectedPathError(DockerRuntimeError):
    """Raised when a tool tries to modify protected runtime metadata."""
