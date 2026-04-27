# pylint: disable-all
import os
import sys
import uuid
import ctypes
import ctypes.wintypes
import logging

from win32com.shell import shell, shellcon  # type: ignore
from win32com.propsys import propsys, pscon  # type: ignore
import winnt
import pythoncom
import pywintypes
import win32api

from minecraftlauncher import config
from minecraftlauncher.front import resources
from minecraftlauncher.back import profile_manager
from minecraftlauncher.datatypes import GameProfile
from minecraftlauncher.constants import AUTHOR_USR, LAUNCHER_NAME

log = logging.getLogger(__name__)

type Unknown = object

EXE_PATH = win32api.GetModuleFileName(0)


def set_jump_list():  # TODO: rename to build_jump_list()
    """
    MS Learn:<br>
    https://learn.microsoft.com/en-us/windows/win32/api/shlobj_core

    objects used:
    - SHARD (enum)
    - SHAddToRecentDocs()

    This function has a lot of `# type: ignore` in it, maybe there's a better
    way to do it that doesn't piss off the type-checker?
    """
    if not profile_manager.profiles:
        log.warning("set_jump_list() called before profiles are loaded!")

    profile_links = []
    rm_from_config = []  # list of IDs to remove from the config file

    log.debug("Setting up CustomDestinationList object")
    jump_list = pythoncom.CoCreateInstance(  # type: ICustomDestinationList
        shell.CLSID_DestinationList,
        None,
        pythoncom.CLSCTX_INPROC_SERVER,
        shell.IID_ICustomDestinationList,
    )

    jump_list.SetAppID(f"{AUTHOR_USR}.{LAUNCHER_NAME}")  # type: ignore

    max_items: int
    max_items, removed_array = jump_list.BeginList()  # type: ignore

    # get the items the user manually unpinned through the shell (if any):
    for i in range(removed_array.GetCount()):
        rm_link = removed_array.GetAt(i, shell.IID_IShellLink)  # IShellLink

        prof_id = str(rm_link.GetArguments()).split("=")[1].strip()
        rm_from_config.append(prof_id)

    for item in rm_from_config:
        try:
            config.jump_list_items.remove(item)
        except ValueError:
            log.warning(
                "Profile with ID %s either doesn't exist, or was incorrectly "
                "in jump list items.",
                item,
            )
            pass

    for profile_id in config.jump_list_items:
        if profile_id not in profile_manager.profiles:
            log.warning("Profile %s doesn't exist!", profile_id)
            rm_from_config.append(profile_id)
            continue
        profile = profile_manager.get_profile(profile_id)
        link = pythoncom.CoCreateInstance(  # type: PyIShellLink
            shell.CLSID_ShellLink,
            None,
            pythoncom.CLSCTX_INPROC_SERVER,
            shell.IID_IShellLink,
        )

        link.SetArguments(f"--launch-profile={profile.uuid}")  # type: ignore

        if profile.icon:
            ico_path = resources.cache_icon(
                resources.profile_icon(profile.icon), profile.uuid
            )
            log.debug("Trying to set the link's icon")
            link.SetIconLocation(ico_path, 0)  # type: ignore

        log.debug("Attempting to set link path to '%s'", EXE_PATH)
        link.SetPath(EXE_PATH)  # type: ignore

        log.debug("Setting the lnk name")
        ps = link.QueryInterface(propsys.IID_IPropertyStore)
        title_pk = pscon.PKEY_Title
        ps.SetValue(  # type: ignore
            title_pk,
            propsys.PROPVARIANTType(f"Start {profile.name}"),
        )
        ps.Commit()  # type: ignore

        log.debug("Setting the description to the profile ID")
        link.SetDescription(  # type: ignore
            f"Opens the launcher and immediately starts {profile.name}"
        )
        profile_links.append(link)

    if profile_links:
        collection = pythoncom.CoCreateInstance(
            shell.CLSID_EnumerableObjectCollection,
            None,
            pythoncom.CLSCTX_INPROC_SERVER,
            shell.IID_IObjectCollection,
        )

        for link in profile_links[:max_items]:
            collection.AddObject(link)  # type: ignore

        task_array = collection.QueryInterface(shell.IID_IObjectArray)
        jump_list.AddUserTasks(task_array)  # type: ignore
    else:
        log.debug("No tasks to add, committing empty list.")
    jump_list.CommitList()  # type: ignore
    return
