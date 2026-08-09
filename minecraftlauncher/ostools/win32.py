# pylint: disable=e1101,e0401
import ctypes
import logging

from win32com.shell import shell  # type: ignore
from win32com.propsys import propsys, pscon  # type: ignore
import pythoncom
import win32api

from minecraftlauncher.config import config
from minecraftlauncher.front import resources
from minecraftlauncher.back import profile_manager
from minecraftlauncher.constants import APP_SLUG, DEV, OS

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
        return

    profile_links = []
    config_removal_queue = []  # list of IDs to remove from the config file

    jump_list = pythoncom.CoCreateInstance(  # type: ICustomDestinationList
        shell.CLSID_DestinationList,
        None,
        pythoncom.CLSCTX_INPROC_SERVER,
        shell.IID_ICustomDestinationList,
    )

    jump_list.SetAppID(APP_SLUG)  # type: ignore

    max_items: int
    max_items, removed_array = jump_list.BeginList()  # type: ignore

    # get the items the user manually unpinned through the shell (if any):
    for i in range(removed_array.GetCount()):
        rm_link = removed_array.GetAt(i, shell.IID_IShellLink)  # IShellLink

        prof_id = str(rm_link.GetArguments()).split("=")[1].strip()
        config_removal_queue.append(prof_id)

    for item in config_removal_queue:
        try:
            config.jump_list_items.remove(item)
        except ValueError:
            log.warning(
                "Profile with ID %s either doesn't exist, or was incorrectly "
                "in jump list items.",
                item,
            )

    for profile_id in config.jump_list_items:
        if profile_id not in profile_manager.profiles:
            log.warning("Profile %s doesn't exist!", profile_id)
            config_removal_queue.append(profile_id)
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
            link.SetIconLocation(ico_path, 0)  # type: ignore

        link.SetPath(EXE_PATH)  # type: ignore

        ps = link.QueryInterface(propsys.IID_IPropertyStore)
        title_pk = pscon.PKEY_Title
        ps.SetValue(  # type: ignore
            title_pk,
            propsys.PROPVARIANTType(f"Start {profile.name}"),
        )
        ps.Commit()  # type: ignore

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

        log.debug("Committing task list")
        task_array = collection.QueryInterface(shell.IID_IObjectArray)
        jump_list.AddUserTasks(task_array)  # type: ignore
    else:
        log.debug("No tasks to add, committing empty list.")
    jump_list.CommitList()  # type: ignore
    return


def setup_app_id():
    if not DEV:
        match OS:
            case "windows":
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                    APP_SLUG
                )
