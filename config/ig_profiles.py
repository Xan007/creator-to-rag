"""Compatibility shim for config.profiles.

All profile configuration logic is consolidated in config.profiles (ProfileConfig).
This module re-exports aliases to preserve backwards compatibility.
"""
from config.profiles import (
    ProfileConfig as IGProfileInfo,
    load_profile as load_ig_profile,
    save_profile as save_ig_profile,
    delete_profile as delete_ig_profile,
)

__all__ = [
    "IGProfileInfo",
    "load_ig_profile",
    "save_ig_profile",
    "delete_ig_profile",
]
