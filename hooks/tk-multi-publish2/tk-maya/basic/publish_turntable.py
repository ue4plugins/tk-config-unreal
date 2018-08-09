# This file is based on templates provided and copyrighted by Autodesk, Inc.
# This file has been modified by Epic Games, Inc. and is subject to the license 
# file included in this repository.

import os
import maya.cmds as cmds
import maya.mel as mel
import pprint
import sgtk
import subprocess
import sys

HookBaseClass = sgtk.get_hook_baseclass()

class MayaUnrealTurntablePublishPlugin(HookBaseClass):
    """
    Plugin for publishing an open maya session as an exported FBX.

    This hook relies on functionality found in the base file publisher hook in
    the publish2 app and should inherit from it in the configuration. The hook
    setting for this plugin should look something like this::

        hook: "{self}/publish_file.py:{engine}/tk-multi-publish2/basic/publish_session.py"

    """

    # NOTE: The plugin icon and name are defined by the base file plugin.

    @property
    def description(self):
        """
        Verbose, multi-line description of what the plugin does. This can
        contain simple html for formatting.
        """

        loader_url = "https://support.shotgunsoftware.com/hc/en-us/articles/219033078"

        return """
        <p>This plugin renders a turntable of the asset for the current session
        in Unreal Engine.  The asset will be exported to FBX and imported into
        an Unreal Project for rendering turntables.  A command line Unreal render
        will then be initiated and output to a templated location on disk.  Then,
        the turntable render will be published to Shotgun and submitted for review
        as a Version.</p>
        """

    @property
    def settings(self):
        """
        Dictionary defining the settings that this plugin expects to receive
        through the settings parameter in the accept, validate, publish and
        finalize methods.

        A dictionary on the following form::

            {
                "Settings Name": {
                    "type": "settings_type",
                    "default": "default_value",
                    "description": "One line description of the setting"
            }

        The type string should be one of the data types that toolkit accepts as
        part of its environment configuration.
        """

        # inherit the settings from the base publish plugin
        base_settings = super(MayaUnrealTurntablePublishPlugin, self).settings or {}

        # settings specific to this class
        maya_publish_settings = {
            "Publish Template": {
                "type": "template",
                "default": None,
                "description": "Template path for published work files. Should"
                               "correspond to a template defined in "
                               "templates.yml.",
            }
        }

        work_template_setting = {
            "Work Template": {
                "type": "template",
                "default": None,
                "description": "Template path for exported FBX files. Should"
                               "correspond to a template defined in "
                               "templates.yml.",
            }
        }

        unreal_engine_version_setting = {
            "Unreal Engine Version": {
                "type": "string",
                "default": None,
                "description": "Version of the Unreal Engine exectuable to use."
            }
        }
        
        unreal_project_path_setting = {
            "Unreal Project Path": {
                "type": "string",
                "default": None,
                "description": "Path to the Unreal project to load."
            }
        }

        turntable_map_path_setting = {
            "Turntable Map Path": {
                "type": "string",
                "default": None,
                "description": "Unreal path to the turntable map to use to render the turntable."
            }
        }
        
        sequence_path_setting = {
            "Sequence Path": {
                "type": "string",
                "default": None,
                "description": "Unreal path to the level sequence to use to render the turntable."
            }
        }

        assets_output_path_setting = {
            "Turntable Assets Path": {
                "type": "string",
                "default": None,
                "description": "Unreal output path where the turntable assets will be imported."
            }
        }

        # update the base settings
        base_settings.update(maya_publish_settings)
        base_settings.update(work_template_setting)
        base_settings.update(unreal_engine_version_setting)
        base_settings.update(unreal_project_path_setting)
        base_settings.update(turntable_map_path_setting)
        base_settings.update(sequence_path_setting)
        base_settings.update(assets_output_path_setting)

        return base_settings

    @property
    def item_filters(self):
        """
        List of item types that this plugin is interested in.

        Only items matching entries in this list will be presented to the
        accept() method. Strings can contain glob patters such as *, for example
        ["maya.*", "file.maya"]
        """
        return ["maya.turntable"]

    def accept(self, settings, item):
        """
        Method called by the publisher to determine if an item is of any
        interest to this plugin. Only items matching the filters defined via the
        item_filters property will be presented to this method.

        A publish task will be generated for each item accepted here. Returns a
        dictionary with the following booleans:

            - accepted: Indicates if the plugin is interested in this value at
                all. Required.
            - enabled: If True, the plugin will be enabled in the UI, otherwise
                it will be disabled. Optional, True by default.
            - visible: If True, the plugin will be visible in the UI, otherwise
                it will be hidden. Optional, True by default.
            - checked: If True, the plugin will be checked in the UI, otherwise
                it will be unchecked. Optional, True by default.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process

        :returns: dictionary with boolean keys accepted, required and enabled
        """

        # if a publish template is configured, disable context change. This
        # is a temporary measure until the publisher handles context switching
        # natively.
        if settings.get("Publish Template").value:
            item.context_change_allowed = False

        path = _session_path()

        if not path:
            # the session has not been saved before (no path determined).
            # provide a save button. the session will need to be saved before
            # validation will succeed.
            self.logger.warn(
                "The Maya session has not been saved.",
                extra=_get_save_as_action()
            )

        self.logger.info(
            "Maya '%s' plugin accepted the current Maya session." %
            (self.name,)
        )
        return {
            "accepted": True,
            "checked": True
        }

    def validate(self, settings, item):
        """
        Validates the given item to check that it is ok to publish. Returns a
        boolean to indicate validity.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        :returns: True if item is valid, False otherwise.
        """

        # Validate the Unreal executable and project
        unreal_exec_path = self.get_unreal_project_path() or self._get_unreal_exec_path(settings)
        if not unreal_exec_path or not os.path.isfile(unreal_exec_path):
            self.logger.error("Unreal executable not found at {}".format(unreal_exec_path))
            return False

        # Use the Unreal project path override if it's defined, otherwise use the path from the settings
        unreal_project_path = self.get_unreal_project_path() or self._get_unreal_project_path(settings)
        if not unreal_project_path or not os.path.isfile(unreal_project_path):
            self.logger.error("Unreal project not found at {}".format(unreal_project_path))
            return False

        publisher = self.parent
        path = _session_path()

        # ---- ensure the session has been saved

        if not path:
            # the session still requires saving. provide a save button.
            # validation fails.
            error_msg = "The Maya session has not been saved."
            self.logger.error(
                error_msg,
                extra=_get_save_as_action()
            )
            raise Exception(error_msg)

        # ensure we have an updated project root
        project_root = cmds.workspace(q=True, rootDirectory=True)
        item.properties["project_root"] = project_root

        # log if no project root could be determined.
        if not project_root:
            self.logger.info(
                "Your session is not part of a maya project.",
                extra={
                    "action_button": {
                        "label": "Set Project",
                        "tooltip": "Set the maya project",
                        "callback": lambda: mel.eval('setProject ""')
                    }
                }
            )

        # ---- check the session against any attached work template

        # get the path in a normalized state. no trailing separator,
        # separators are appropriate for current os, no double separators,
        # etc.
        path = sgtk.util.ShotgunPath.normalize(path)

        # Validate the Unreal data settings
        turntable_map_path_setting = settings.get("Turntable Map Path")
        turntable_map_path = turntable_map_path_setting.value if turntable_map_path_setting else None
        if not turntable_map_path:
            self.logger.debug("No Unreal turntable map configured.")
            return False

        sequence_path_setting = settings.get("Sequence Path")
        sequence_path = sequence_path_setting.value if sequence_path_setting else None
        if not sequence_path:
            self.logger.debug("No Unreal turntable sequence configured.")
            return False

        unreal_content_browser_path_setting = settings.get("Turntable Assets Path")
        unreal_content_browser_path = unreal_content_browser_path_setting.value if unreal_content_browser_path_setting else None
        if not unreal_content_browser_path:
            self.logger.debug("No Unreal turntable assets output path configured.")
            return False
            
        # if the session item has a known work template, see if the path
        # matches. if not, warn the user and provide a way to save the file to
        # a different path
        work_template_setting = settings.get("Work Template")
        work_template = publisher.get_template_by_name(work_template_setting.value)
        if work_template:
            item.properties["work_template"] = work_template
            self.logger.debug(
                "Work template configured as {}.".format(work_template))
        else:
            self.logger.debug("No work template configured.")
            return False

        # ---- see if the version can be bumped post-publish

        # check to see if the next version of the work file already exists on
        # disk. if so, warn the user and provide the ability to jump to save
        # to that version now
        (next_version_path, version) = self._get_next_version_info(path, item)
        if next_version_path and os.path.exists(next_version_path):

            # determine the next available version_number. just keep asking for
            # the next one until we get one that doesn't exist.
            while os.path.exists(next_version_path):
                (next_version_path, version) = self._get_next_version_info(
                    next_version_path, item)

            error_msg = "The next version of this file already exists on disk."
            self.logger.error(
                error_msg,
                extra={
                    "action_button": {
                        "label": "Save to v%s" % (version,),
                        "tooltip": "Save to the next available version number, "
                                   "v%s" % (version,),
                        "callback": lambda: _save_session(next_version_path)
                    }
                }
            )
            raise Exception(error_msg)

        # ---- populate the necessary properties and call base class validation

        # populate the publish template on the item if found
        publish_template_setting = settings.get("Publish Template")
        publish_template = publisher.engine.get_template_by_name(
            publish_template_setting.value)
        if publish_template:
            item.properties["publish_template"] = publish_template
        else:
            self.logger.debug("No published template configured.")
            return False

        # This plugin publishes a turntable movie to Shotgun
        # These are the steps needed to do that

        # =======================
        # 1. Export the Maya scene to FBX
        # The FBX will be exported to the current session folder, but any other destination folder could be specified instead
        
        # get the path in a normalized state. no trailing separator, separators
        # are appropriate for current os, no double separators, etc.
        path = sgtk.util.ShotgunPath.normalize(_session_path())

        # ensure the session is saved
        _save_session(path)

        # Extract the filename from the work path
        path_components = os.path.split(path)
        destination_path = path_components[0]
        filename = path_components[1]

        # Ensure that the destination path exists before rendering the sequence
        self.parent.ensure_folder_exists(destination_path)

        # Replace file extension with .fbx and suffix it witn "_turntable"
        asset_name = os.path.splitext(filename)[0] + "_turntable"
        fbx_name = asset_name + ".fbx"
        fbx_output_path = os.path.join(destination_path, fbx_name)
        
        # Export to FBX to given output path
        if not self._maya_export_fbx(fbx_output_path):
            return False

        # Keep the fbx path for cleanup at finalize
        item.properties["temp_fbx_path"] =  fbx_output_path
        
        # =======================
        # 2. Import the FBX into Unreal.
        # 3. Instantiate the imported asset into a duplicate of the turntable map.
        # Use the unreal_setup_turntable to do this in Unreal

        current_folder = os.path.dirname( __file__ )
        script_name = "../unreal/unreal_setup_turntable.py"
        script_path = os.path.join(current_folder, script_name)
        script_path = os.path.abspath(script_path)

        script_args = []
        
        # The FBX to import into Unreal
        script_args.append(fbx_output_path)
        
        # The Unreal content browser folder where the asset will be imported into
        script_args.append(unreal_content_browser_path)

        # The Unreal turntable map to duplicate where the asset will be instantiated into
        script_args.append(turntable_map_path)

        self._unreal_execute_script(unreal_exec_path, unreal_project_path, script_path, script_args)
        
        # =======================
        # 4. Render the turntable to movie.
        # Output the movie to the work path
        work_path_fields = {"name" : asset_name}
        work_path = work_template.apply_fields(work_path_fields)
        work_path = os.path.normpath(work_path)

        # Remove the filename from the work path
        destination_path = os.path.split(work_path)[0]

        # Ensure that the destination path exists before rendering the sequence
        self.parent.ensure_folder_exists(destination_path)

        success, output_filepath = self._unreal_render_sequence_to_movie(unreal_exec_path, unreal_project_path, turntable_map_path, sequence_path, destination_path, asset_name)
        
        if not success:
            return False

        item.properties["path"] = output_filepath.replace("/", "\\")
        item.properties["publish_name"] = asset_name
        
        # run the base class validation
        # return super(MayaUnrealTurntablePublishPlugin, self).validate(settings, item)
        
        return True

    def publish(self, settings, item):
        """
        Executes the publish logic for the given item and settings.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """

        # Publish the turntable movie file to Shotgun
        super(MayaUnrealTurntablePublishPlugin, self).publish(settings, item)
        
        # Create a Version entry linked with the new publish
        publish_name = item.properties.get("publish_name")
        
        # Populate the version data to send to SG
        self.logger.info("Creating Version...")
        version_data = {
            "project": item.context.project,
            "code": publish_name,
            "description": item.description,
            "entity": self._get_version_entity(item),
            "sg_task": item.context.task
        }

        publish_data = item.properties.get("sg_publish_data")

        # If the file was published, add the publish data to the version
        if publish_data:
            version_data["published_files"] = [publish_data]

        # Log the version data for debugging
        self.logger.debug(
            "Populated Version data...",
            extra={
                "action_show_more_info": {
                    "label": "Version Data",
                    "tooltip": "Show the complete Version data dictionary",
                    "text": "<pre>%s</pre>" % (
                    pprint.pformat(version_data),)
                }
            }
        )

        # Create the version
        self.logger.info("Creating version for review...")
        version = self.parent.shotgun.create("Version", version_data)

        # Stash the version info in the item just in case
        item.properties["sg_version_data"] = version

        # On windows, ensure the path is utf-8 encoded to avoid issues with
        # the shotgun api
        upload_path = item.properties.get("path")
        if sys.platform.startswith("win"):
            upload_path = upload_path.decode("utf-8")

        # Upload the file to SG
        self.logger.info("Uploading content...")
        self.parent.shotgun.upload(
            "Version",
            version["id"],
            upload_path,
            "sg_uploaded_movie"
        )
        self.logger.info("Upload complete!")
        
    def finalize(self, settings, item):
        """
        Execute the finalization pass. This pass executes once all the publish
        tasks have completed, and can for example be used to version up files.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """

        # do the base class finalization
        super(MayaUnrealTurntablePublishPlugin, self).finalize(settings, item)

        # bump the session file to the next version
        # self._save_to_next_version(item.properties["maya_path"], item, _save_session)
        
        # Delete the exported FBX
        fbx_path = item.properties.get("temp_fbx_path")
        if fbx_path:
            try:
                os.remove(fbx_path)
            except:
                pass

    def _get_version_entity(self, item):
        """
        Returns the best entity to link the version to.
        """
        if item.context.entity:
            return item.context.entity
        elif item.context.project:
            return item.context.project
        else:
            return None
        
    def _maya_export_fbx(self, fbx_output_path):
        # Export scene to FBX
        try:
            self.logger.info("Exporting scene to FBX {}".format(fbx_output_path))
            cmds.FBXResetExport()
            cmds.FBXExportSmoothingGroups('-v', True)
            # Mel script equivalent: mel.eval('FBXExport -f "fbx_output_path"')
            cmds.FBXExport('-f', fbx_output_path)
        except:
            self.logger.error("Could not export scene to FBX")
            return False
            
        return True
        
    def _unreal_execute_script(self, unreal_exec_path, unreal_project_path, script_path, script_args):
        command_args = []
        command_args.append(unreal_exec_path)       # Unreal executable path
        command_args.append(unreal_project_path)    # Unreal project
        
        command_args.append('-ExecutePythonScript="{} {}"'.format(script_path, " ".join(script_args)))
        self.logger.info("Executing script in Unreal with arguments: {}".format(command_args))
        
        subprocess.call(" ".join(command_args))

    def _unreal_render_sequence_to_movie(self, unreal_exec_path, unreal_project_path, unreal_map_path, sequence_path, destination_path, movie_name):
        """
        Renders a given sequence in a given level to a movie file
        
        :param destination_path: Destionation folder where to generate the movie file
        :param unreal_map_path: Path of the Unreal map in which to run the sequence
        :param sequence_path: Content Browser path of sequence to render
        :param movie_name: Filename of the movie that will be generated
        :returns: True if a movie file was generated, False otherwise
                  string representing the path of the generated movie file
        """
        # First, check if there's a file that will interfere with the output of the Sequencer
        # Sequencer can only render to avi file format
        output_filename = "{}.avi".format(movie_name)
        output_filepath = os.path.join(destination_path, output_filename)

        if os.path.isfile(output_filepath):
            # Must delete it first, otherwise the Sequencer will add a number in the filename
            try:
                os.remove(output_filepath)
            except OSError, e:
                self.logger.debug("Couldn't delete {}. The Sequencer won't be able to output the movie to that file.".format(output_filepath))
                return False, None

        # Render the sequence to a movie file using the following command-line arguments
        cmdline_args = []
        
        # Note that any command-line arguments (usually paths) that could contain spaces must be enclosed between quotes

        # Important to keep the order for these arguments
        cmdline_args.append(unreal_exec_path)       # Unreal executable path
        cmdline_args.append(unreal_project_path)    # Unreal project
        cmdline_args.append(unreal_map_path)        # Level to load for rendering the sequence
        
        # Command-line arguments for Sequencer Render to Movie
        # See: https://docs.unrealengine.com/en-us/Engine/Sequencer/Workflow/RenderingCmdLine
        sequence_path = "-LevelSequence={}".format(sequence_path)
        cmdline_args.append(sequence_path)          # The sequence to render
        
        output_path = '-MovieFolder="{}"'.format(destination_path)
        cmdline_args.append(output_path)            # output folder, must match the work template

        movie_name_arg = "-MovieName={}".format(movie_name)
        cmdline_args.append(movie_name_arg)         # output filename
        
        cmdline_args.append("-game")
        cmdline_args.append("-MovieSceneCaptureType=/Script/MovieSceneCapture.AutomatedLevelSequenceCapture")
        cmdline_args.append("-ResX=1280")
        cmdline_args.append("-ResY=720")
        cmdline_args.append("-ForceRes")
        cmdline_args.append("-Windowed")
        cmdline_args.append("-MovieCinematicMode=yes")
        cmdline_args.append("-MovieFormat=Video")
        cmdline_args.append("-MovieFrameRate=24")
        cmdline_args.append("-MovieQuality=75")
        cmdline_args.append("-MovieWarmUpFrames=30")
        cmdline_args.append("-NoTextureStreaming")
        cmdline_args.append("-NoLoadingScreen")
        cmdline_args.append("-NoScreenMessages")

        self.logger.info("Sequencer command-line arguments: {}".format(cmdline_args))
        
        # Send the arguments as a single string because some arguments could contain spaces and we don't want those to be quoted
        subprocess.call(" ".join(cmdline_args))

        return os.path.isfile(output_filepath), output_filepath

    def _get_unreal_exec_path(self, settings):
        """
        Return the path to the Unreal Engine executable to use
        Uses the Engine Launcher logic to scan for Unreal executables and selects the one that
        matches the version defined in the settings, prioritizing non-development builds
        :returns an absolute path to the Unreal Engine executable to use:
        """
        unreal_engine_version_setting = settings.get("Unreal Engine Version")
        unreal_engine_version = unreal_engine_version_setting.value if unreal_engine_version_setting else None
        
        if not unreal_engine_version:
            return None

        # Create a launcher for the current context
        engine = sgtk.platform.current_engine()
        software_launcher = sgtk.platform.create_engine_launcher(engine.sgtk, engine.context, "tk-unreal")

        # Discover which versions of Unreal are available
        software_versions = software_launcher.scan_software()
        valid_versions = []
        for software_version in software_versions:
            if software_version.version.startswith(unreal_engine_version):
                # Insert non-dev builds at the start of the list
                if "(Dev Build)" not in software_version.display_name:
                    valid_versions.insert(0, software_version)
                else:
                    valid_versions.append(software_version)

        # Take the first valid version
        if valid_versions:
            return valid_versions[0].path
            
        return None

    def _get_unreal_project_path(self, settings):
        """
        Return the path to the Unreal project to use based on the "Unreal Project Path" and
        "Unreal Engine Version" settings. It uses the same path resolution as for hook paths
        to expand {config} and {engine} to their absolute path equivalent.
        :returns an absolute path to the Unreal project to use:
        """
        unreal_project_path_setting = settings.get("Unreal Project Path")
        unreal_project_path = unreal_project_path_setting.value if unreal_project_path_setting else None
        if not unreal_project_path:
            return None

        unreal_engine_version_setting = settings.get("Unreal Engine Version")
        unreal_engine_version = unreal_engine_version_setting.value if unreal_engine_version_setting else None
        if unreal_engine_version:
            unreal_project_path = unreal_project_path.replace("{unreal_engine_version}", unreal_engine_version)
        
        if unreal_project_path.startswith("{config}"):
            hooks_folder = self.sgtk.pipeline_configuration.get_hooks_location()
            unreal_project_path = unreal_project_path.replace("{config}", hooks_folder)
        elif unreal_project_path.startswith("{engine}"):
            engine = sgtk.platform.current_engine()
            engine_hooks_path = os.path.join(engine.disk_location, "hooks")
            unreal_project_path = unreal_project_path.replace("{engine}", engine_hooks_path)

        return os.path.normpath(unreal_project_path)
        
    def get_unreal_exec_path(self):
        """
        Return the path to the Unreal Engine executable to use
        Override this function in a custom hook derived from this class to implement your own logic
        or override the path from the settings
        :returns an absolute path to the Unreal Engine executable to use; None to use the path from the settings:
        """
        return None
        
    def get_unreal_project_path(self):
        """
        Return the path to the Unreal project to use
        Override this function in a custom hook derived from this class to implement your own logic
        or override the path from the settings
        :returns an absolute path to the Unreal project to use; None to use the path from the settings:
        """
        return None
        
def _get_work_path(path, work_template):
    """
    Return the equivalent work path with the filename from path applied to the work template
    :param path: An absulote path with a filename
    :param work_template: A template to use to get the work path
    :returns a work path:
    """
    # Get the filename from the path
    filename = os.path.split(path)[1]
    
    # Retrieve the name field from the filename excluding the extension
    work_path_fields = {"name" : os.path.splitext(filename)[0]}
    
    # Apply the name to the work template
    work_path = work_template.apply_fields(work_path_fields)
    work_path = os.path.normpath(work_path)

    return work_path

def _session_path():
    """
    Return the path to the current session
    :return:
    """
    path = cmds.file(query=True, sn=True)

    if isinstance(path, unicode):
        path = path.encode("utf-8")

    return path


def _save_session(path):
    """
    Save the current session to the supplied path.
    """

    # Maya can choose the wrong file type so we should set it here
    # explicitly based on the extension
    maya_file_type = None
    if path.lower().endswith(".ma"):
        maya_file_type = "mayaAscii"
    elif path.lower().endswith(".mb"):
        maya_file_type = "mayaBinary"

    cmds.file(rename=path)

    # save the scene:
    if maya_file_type:
        cmds.file(save=True, force=True, type=maya_file_type)
    else:
        cmds.file(save=True, force=True)


# TODO: method duplicated in all the maya hooks
def _get_save_as_action():
    """
    Simple helper for returning a log action dict for saving the session
    """

    engine = sgtk.platform.current_engine()

    # default save callback
    callback = cmds.SaveScene

    # if workfiles2 is configured, use that for file save
    if "tk-multi-workfiles2" in engine.apps:
        app = engine.apps["tk-multi-workfiles2"]
        if hasattr(app, "show_file_save_dlg"):
            callback = app.show_file_save_dlg

    return {
        "action_button": {
            "label": "Save As...",
            "tooltip": "Save the current session",
            "callback": callback
        }
    }
