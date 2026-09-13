class AppLauncherError(Exception):
    """Base class for all app launcher errors."""
class AppNotFoundError(AppLauncherError):
    """Raised when the specified application is not found."""

class TargetFileNotFoundError(AppLauncherError):
    """Raised when the specified target file is not found."""

class ApplicationNotFoundError(AppLauncherError):
    """Raised when the specified application is not found."""

class AmbiguousApplicationError(AppLauncherError):
    """Raised when multiple applications match the specified criteria."""
    
class RegistrationError(AppLauncherError):
    """Raised when there is an error during the registration process."""