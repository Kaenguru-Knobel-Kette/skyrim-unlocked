import logging
import os
import pathlib
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree

"""Valid extensions of a plugin."""
plugin_exts = [".esl", ".esp", ".esm"]

"""All files in these directories will be included in a bsa."""
bsa_include_dirs = ["interface", "meshes", "music", "textures", "scripts",
                    "seq", "shadersfx", "sound", "strings"]


class ArchiveFlags():
    """Flags for Archive.exe"""

    def __init__(self):
        self.check_meshes = False
        self.check_textures = False
        self.check_menus = False
        self.check_sounds = False
        self.check_voices = False
        self.check_shaders = False
        self.check_trees = False
        self.check_fonts = False
        self.check_misc = False
        self.check_compress_archive = False
        self.check_retain_directory_names = False
        self.check_retain_file_names = False
        self.check_retain_file_name_offsets = False
        self.check_retain_strings_during_startup = False
        self.check_embed_file_name = False


def build_release(dir_source, dir_target, archive_exe=None,
                  archive_flags=None):
    """Build a release archive.

    Args:
        dir_source: The source directory for which the archive is built.
            It must contain a Fomod subdirectory with Info.xml and
            ModuleConfig.xml.
            Furthermore it must contain a subdirectory for every folder
            specified in ModuleConfig.xml. Such a subdirectory is expected
            to contain at most one plugin.
        dir_target: The target directory for the release archive.
        archive_exe: The executable that creates the bsa.
            If ommited no bsa will be created.
        archive_flags: Check the corresponding options in Archive.exe
            If ommited no flags will be set.
    """
    logger = logging.getLogger(build_release.__name__)
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(build_release.__name__ + ".log")
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.info("------------------------------------------------------------")
    logger.info("Building release")
    logger.info("Source directory: " + dir_source)
    logger.info("Target directory: " + dir_target)
    logger.info("Build bsa: " + str(bool(archive_exe)))
    # Validate arguments
    dir_source_fomod = os.path.join(dir_source, "Fomod")
    if not os.path.isdir(dir_source):
        logger.error("Source directory does not exist")
        exit()
    if not os.path.isdir(dir_target):
        logger.error("Target directory does not exist")
        exit()
    if not os.path.isfile(os.path.join(dir_source_fomod, "Info.xml")):
        logger.error("Info.xml is missing in " + dir_source_fomod)
        exit()
    if not os.path.isfile(os.path.join(dir_source_fomod, "ModuleConfig.xml")):
        logger.error("ModuleConfig.xml is missing in " + dir_source_fomod)
        exit()
    if archive_exe and not os.path.isfile(archive_exe):
        logger.error("Archive.exe path " + archive_exe + " does not exist")
        exit()
    if archive_exe and os.path.basename(archive_exe) != "Archive.exe":
        logger.error(archive_exe + " does not point to Archive.exe")
        exit()
    # Get required subdirectories from ModuleConfig.xml
    path = os.path.join(dir_source_fomod, "ModuleConfig.xml")
    root = xml.etree.ElementTree.parse(path).getroot()
    sub_dirs = list()
    for installSteps in root.iterfind("installSteps"):
        for installStep in installSteps.iterfind("installStep"):
            for fileGroups in installStep.iterfind("optionalFileGroups"):
                for group in fileGroups.iterfind("group"):
                    for plugins in group.iterfind("plugins"):
                        for plugin in plugins.iterfind("plugin"):
                            for files in plugin.iterfind("files"):
                                for folder in files.iterfind("folder"):
                                    sub_dirs.append(folder.get("source"))
    # Validate subdirectories
    logger.info("Subdirectories required by the Fomod installer:")
    for sub_dir in sub_dirs:
        logger.info("   " + sub_dir)
        if not os.path.isdir(os.path.join(dir_source, sub_dir)):
            logger.error("Subdirectory " + sub_dir + " is missing")
            exit()
        if len(find_plugins(os.path.join(dir_source, sub_dir))) > 1:
            logger.warning("Subdirectory " + sub_dir +
                           " contains multiple plugins")
    # Get version number and release name from Info.xml
    path = os.path.join(dir_source_fomod, "Info.xml")
    root = xml.etree.ElementTree.parse(path).getroot()
    version = root.find("Version").text
    name_release = root.find("Name").text
    # Validate version stamp of plugins
    version_stamp = bytes("Version: " + version, "utf8")
    for sub_dir in sub_dirs:
        for plugin in find_plugins(os.path.join(dir_source, sub_dir)):
            path_plugin = os.path.join(dir_source, sub_dir, plugin)
            with open(path_plugin, "rb") as fh:
                if version_stamp not in fh.read():
                    logger.warning(plugin +
                                   " does not have the correct version stamp")
    # Build fomod tree in a temporary directory
    with tempfile.TemporaryDirectory() as dir_temp:
        # Copy fomod files to the fomod tree
        src = os.path.join(dir_source, "Fomod")
        dst = os.path.join(dir_temp, "Fomod")
        shutil.copytree(src, dst)
        # Copy subdirectories to the fomod tree
        for sub_dir in sub_dirs:
            plugins = find_plugins(os.path.join(dir_source, sub_dir))
            if plugins and archive_exe:
                # Create subdirectory
                os.mkdir(os.path.join(dir_temp, sub_dir))
                # Copy only the plugin
                file_plugin = plugins[0]
                src = os.path.join(dir_source, sub_dir, file_plugin)
                dst = os.path.join(dir_temp, sub_dir, file_plugin)
                shutil.copy(src, dst)
                # Copy associated ini file (if present)
                file_ini = os.path.splitext(file_plugin)[0] + ".ini"
                src = os.path.join(dir_source, sub_dir, file_ini)
                dst = os.path.join(dir_temp, sub_dir, file_ini)
                if os.path.isfile(src):
                    shutil.copy(src, dst)
                # Build the bsa
                file_bsa = os.path.splitext(file_plugin)[0] + ".bsa"
                src = os.path.join(dir_source, sub_dir)
                dst = os.path.join(dir_temp, sub_dir, file_bsa)
                if archive_flags:
                    build_bsa(archive_exe, src, dst, archive_flags)
                else:
                    build_bsa(archive_exe, src, dst, ArchiveFlags())
            else:
                # Copy everything
                src = os.path.join(dir_source, sub_dir)
                dst = os.path.join(dir_temp, sub_dir)
                shutil.copytree(src, dst)
        # Pack fomod tree into a 7zip archive
        file_archive = name_release + " " + version + ".7z"
        # Remove whitespaces from archive name because GitHub doesn't like them
        file_archive = "_".join(file_archive.split())
        src = os.path.join(dir_temp, "*")
        dst = os.path.join(dir_target, file_archive)
        if os.path.isfile(dst):
            os.remove(dst)
        cmd = ["7z", "a", dst, src]
        sp = subprocess.run(cmd, stdout=subprocess.DEVNULL)
        sp.check_returncode()
        logger.info("Succesfully built archive for " + version + " of " +
                    name_release)
    logger.removeHandler(handler)


def build_bsa(archive_exe, dir_source, bsa_target,
              archive_flags: ArchiveFlags):
    """Build a bsa.

    Args:
        archive_exe: Path to Archive.exe, the executable that creates the bsa.
        dir_source: All valid files in this directory are packed into the bsa.
        bsa_target: Target destination of the bsa.
            This is the final path e.g. /Some/Path/Mod.bsa
        archive_flags: Check the corresponding options in Archive.exe
    """
    # Some genius at Bethesda had the idea to assume that the first occurence
    # of "Data" in a path must be Skyrim's Data directory. Thus the temporary
    # directory must not be created at the default location AppData\Temp
    with tempfile.TemporaryDirectory(dir="C:\\Windows\\Temp") as dir_temp:
        # Another genius' idea: The root of the loose files must be Data
        path_root = os.path.join(dir_temp, "Data")
        shutil.copytree(dir_source, path_root)
        # Create manifest
        path_manifest = os.path.join(dir_temp, "Manifest.txt")
        with open(path_manifest, "w") as manifest:
            for root, subdirs, files in os.walk(dir_source):
                root_relative = pathlib.PurePath(root).relative_to(dir_source)
                for file in files:
                    path_relative = root_relative.joinpath(file)
                    first_dir = path_relative.parts[0]
                    if first_dir.lower() in bsa_include_dirs:
                        manifest.write(str(path_relative) + "\n")
        # Create batch file
        path_batch = os.path.join(dir_temp, "Batch.txt")
        with open(path_batch, "w") as batch:
            path_log = os.path.basename(bsa_target).replace(".bsa", ".log")
            batch.write("Log: " + path_log + "\n")
            batch.write("New Archive\n")
            if archive_flags.check_meshes:
                batch.write("Check: Meshes\n")
            if archive_flags.check_textures:
                batch.write("Check: Textures\n")
            if archive_flags.check_menus:
                batch.write("Check: Menus\n")
            if archive_flags.check_sounds:
                batch.write("Check: Sounds\n")
            if archive_flags.check_voices:
                batch.write("Check: Voices\n")
            if archive_flags.check_shaders:
                batch.write("Check: Shaders\n")
            if archive_flags.check_trees:
                batch.write("Check: Trees\n")
            if archive_flags.check_fonts:
                batch.write("Check: Fonts\n")
            if archive_flags.check_misc:
                batch.write("Check: Misc\n")
            if archive_flags.check_compress_archive:
                batch.write("Check: Compress Archive\n")
            if archive_flags.check_retain_directory_names:
                batch.write("Check: Retain Directory Names\n")
            if archive_flags.check_retain_file_names:
                batch.write("Check: Retain File Names\n")
            if archive_flags.check_retain_file_name_offsets:
                batch.write("Check: Retain File Name Offsets\n")
            if archive_flags.check_retain_strings_during_startup:
                batch.write("Check: Retain Strings During Startup\n")
            if archive_flags.check_embed_file_name:
                batch.write("Check: Embed File Names\n")
            batch.write("Set File Group Root: " + path_root + os.sep + "\n")
            batch.write("Add File Group: " + path_manifest + "\n")
            batch.write("Save Archive: " + bsa_target + "\n")
        # Build bsa
        cmd = [archive_exe, path_batch]
        sp = subprocess.run(cmd, stdout=subprocess.DEVNULL)
        sp.check_returncode()
        # Delete useless bsl file
        path_bsl = bsa_target.replace(".bsa", ".bsl")
        os.remove(path_bsl)


def find_plugins(source_dir):
    """Find all plugins in a directory. Does not search in subdirectories."""
    files = os.listdir(source_dir)
    return [f for f in files if os.path.splitext(f)[1] in plugin_exts]
