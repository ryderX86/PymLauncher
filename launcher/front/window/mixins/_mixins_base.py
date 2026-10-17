class BaseWindowMixin:
    """
    Base class for anything utilizing WindowMixins. Alternatively, the fallback
    whenever a platform-specific mixin isn't defined.
    """

    _use_appmodal_: bool

    def __init_subclass__(cls, blocking: bool = True, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._use_appmodal_ = blocking
