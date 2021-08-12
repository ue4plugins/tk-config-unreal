# This file is based on templates provided and copyrighted by Autodesk, Inc.
# This file has been modified by Epic Games, Inc. and is subject to the license 
# file included in this repository.

import sgtk
from tank_vendor import six
from sgtk.platform.qt import QtGui, QtCore
from sgtk.platform import SoftwareVersion

import maya.cmds as cmds

import datetime
import os
import pprint
import re
import shutil
import subprocess
import sys
import tempfile

HookBaseClass = sgtk.get_hook_baseclass()

# Environment variables for turntable script
OUTPUT_PATH_ENVVAR = 'UNREAL_SG_FBX_OUTPUT_PATH'
CONTENT_BROWSER_PATH_ENVVAR = 'UNREAL_SG_CONTENT_BROWSER_PATH'
MAP_PATH_ENVVAR = 'UNREAL_SG_MAP_PATH'

class BrowsablePathWidget(QtGui.QFrame):
    """
    A :class:`QtGui.QFrame` with an input field, an open and a browse button.
    """
    def __init__(self, with_open_button=False, *args, **kwargs):
        """
        Instantiate a new :class:`BrowsablePathWidget`.

        :param bool with_open_button: Whether or not an open button should be
                                      shown.
        """
        super(BrowsablePathWidget, self).__init__(*args, **kwargs)
        self.combo_box = QtGui.QComboBox()
        self.combo_box.setEditable(True)
        self.combo_box.setMaxVisibleItems(10)
        # Prevent the QComboBox to get too big if the path is long.
        self.combo_box.setSizeAdjustPolicy(
            QtGui.QComboBox.AdjustToMinimumContentsLength
        )

        self.open_button = QtGui.QToolButton()
        icon = QtGui.QIcon()
        icon.addPixmap(
            QtGui.QPixmap(":/tk_multi_publish2/file.png"),
            QtGui.QIcon.Normal,
            QtGui.QIcon.Off
        )
        self.open_button.setIcon(icon)
        self.open_button.clicked.connect(self._open_current_path)
        self.combo_box.editTextChanged.connect(self._enable_open_button)
        if not with_open_button:
            # Hide the button if not needed.
            self.open_button.hide()

        self.browse_button = QtGui.QToolButton()
        icon = QtGui.QIcon()
        icon.addPixmap(
            QtGui.QPixmap(":/tk_multi_publish2/browse_white.png"),
            QtGui.QIcon.Normal,
            QtGui.QIcon.Off
        )
        self.browse_button.setIcon(icon)
        self.browse_button.clicked.connect(self._browse)

        layout = QtGui.QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.combo_box)
        layout.addWidget(self.open_button)
        layout.addWidget(self.browse_button)
        self.setLayout(layout)

    @property
    def sgtk(self):
        """
        :returns: A Toolkit API instance retrieved from the current Engine, or
                  ``None``.
        """
        current_engine = sgtk.platform.current_engine()
        if not current_engine:
            return None
        return current_engine.sgtk

    def get_path(self):
        """
        Return the current path value.

        :returns: An utf-8 encoded string.
        """
        return six.ensure_str(self.combo_box.currentText())

    def set_path(self, path):
        """
        Set the current path to the given value.

        :param str path: The path value to set.
        """
        # TODO: this was copied over from another tool where users could enter
        # a path and similar paths were added from matching TK templates. If not
        # needeed, let's remove it.
        self.combo_box.model().clear()
        if path:
            templates = self.sgtk.templates_from_path(path)
            other_paths = []
            for template in templates:
                fields = template.validate_and_get_fields(path, skip_keys=["version"])
                if fields:
                    other_paths.extend(
                        self.sgtk.paths_from_template(
                            template,
                            fields,
                        )
                    )
            if other_paths:
                self.combo_box.addItems(sorted(other_paths, reverse=True))
        # Set the value last to not lose it when setting the combo box items
        self.combo_box.lineEdit().setText(path)

    def _enable_open_button(self, path):
        """
        Enable the open button if a path is set, disable it otherwise.
        """
        self.open_button.setEnabled(bool(path))

    def _open_current_path(self):
        """
        Open the current file in an external application.
        """
        current_path = self.get_path()
        engine = sgtk.platform.current_engine()
        # Would be awesome to use launch app, but launch_from_path does not work
        # in SotfwareEntity mode.
#        if engine and "tk-multi-launchapp" in engine.apps:
#            app = engine.apps["tk-multi-launchapp"]
#            app.launch_from_path(current_path)

        # By default on Mac a single running Maya is used to open new files from
        # desktop services, which could lead to our current scene being replaced
        # when dealing with Maya files. We use `open -n` to force new instances
        # of the application to be used.
        if sys.platform == "darwin":
            os.system("open -n %s" % current_path)
        else:
            QtGui.QDesktopServices.openUrl(
                QtCore.QUrl("file:///%s" % current_path, QtCore.QUrl.TolerantMode)
            )

    def _browse(self, folders=False):
        """
        Opens a file dialog to browse to a file or folders.

        The file dialog can be run in 'folders' mode, which can be useful to
        select sequences of images by selecting the folder they are in.

        :param bool folders: If ``True`` allow to select folders, allow to select
                             a single file otherwise.
        """
        current_path = self.get_path()

        # Options for either browse type
        options = [
            QtGui.QFileDialog.DontResolveSymlinks,
            QtGui.QFileDialog.DontUseNativeDialog
        ]

        if folders:
            # browse folders specifics
            caption = "Browse folders to image sequences"
            file_mode = QtGui.QFileDialog.Directory
            options.append(QtGui.QFileDialog.ShowDirsOnly)
        else:
            # browse files specifics
            # TODO: allow Mac .app folders to be selected instead of having to
            # browse to the UE4Editor.app/Contents/MacOS/UE4Editor file.
            caption = "Browse files"
            file_mode = QtGui.QFileDialog.ExistingFile  # Single file selection

        # Create the dialog
        file_dialog = QtGui.QFileDialog(parent=self, caption=caption)
        file_dialog.setLabelText(QtGui.QFileDialog.Accept, "Select")
        file_dialog.setLabelText(QtGui.QFileDialog.Reject, "Cancel")
        file_dialog.setFileMode(file_mode)

        if current_path:
            # TODO: refine this for folders mode.
            file_dialog.selectFile(current_path)

        for option in options:
            file_dialog.setOption(option)

        if not file_dialog.exec_():
            return

        paths = file_dialog.selectedFiles()
        if paths:
            self.set_path(paths[0])


class UnrealSetupWidget(QtGui.QFrame):
    """
    A :class:`QtGui.QFrame` handling Unreal setup.
    """
    def __init__(self, *args, **kwargs):
        """
        Instantiate a new :class:`UnrealSetupWidget`.
        """
        super(UnrealSetupWidget, self).__init__(*args, **kwargs)
        self._unreal_project_path_template = None
        self.unreal_engine_label = QtGui.QLabel("Unreal Engine:")
        # A ComboBox for detected Unreal versions
        self.unreal_engine_versions_widget = QtGui.QComboBox()
        # Changing the Unreal version updates the executable path and
        # the project path
        self.unreal_engine_versions_widget.currentIndexChanged.connect(
            self._current_unreal_version_changed
        )
        # Let the user pick the Unreal executable from the file system if not
        # automatically detected.
        self.unreal_engine_widget = BrowsablePathWidget()

        # Let the user pick a project path from the file system
        self.unreal_project_label = QtGui.QLabel("Unreal Project Path:")
        self.unreal_project_widget = BrowsablePathWidget()

        settings_layout = QtGui.QVBoxLayout()
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.addWidget(self.unreal_engine_label)
        settings_layout.addWidget(self.unreal_engine_versions_widget)
        settings_layout.addWidget(self.unreal_engine_widget)
        settings_layout.addWidget(self.unreal_project_label)
        settings_layout.addWidget(self.unreal_project_widget)
        self.setLayout(settings_layout)

    @property
    def sgtk(self):
        """
        :returns: A Toolkit API instance retrieved from the current Engine, or
                  ``None``.
        """
        current_engine = sgtk.platform.current_engine()
        if not current_engine:
            return None
        return current_engine.sgtk

    def populate_unreal_versions(self, unreal_versions, current_version):
        """
        Populate the Unreal Versions combo box with the given list of versions.

        Set the selection to the given current version if there is a matching
        version.

        :param unreal_versions: A list of :class:`SoftwareVersion` instances.
        :param current_version: An Unreal version number, as a string.
        """
        for i, unreal_version in enumerate(unreal_versions):
            self.unreal_engine_versions_widget.addItem(
                unreal_version.display_name,
                userData=unreal_version,
            )
            if unreal_version.version == current_version:
                self.unreal_engine_versions_widget.setCurrentIndex(
                    i,
                )
        sel = self.unreal_engine_versions_widget.currentIndex()
        if sel != -1:
            self.unreal_engine_widget.combo_box.lineEdit().setText(
                self.unreal_engine_versions_widget.itemData(sel).path
            )

    def set_unreal_project_path_template(self, project_path_template):
        """
        Set the Unreal project path template used to build a project path from
        the Unreal version and other values.

        :param str project_path_template: A template string.
        """
        self._unreal_project_path_template = project_path_template
        project_path = _evaluate_unreal_project_path(
            project_path_template,
            self.unreal_version,
        ) or ""
        self.unreal_project_widget.set_path(project_path)

    def _current_unreal_version_changed(self, index):
        """
        Called when the Unreal version is changed in the list of versions.

        :param int index: The index of the current selection.
        """
        self.unreal_engine_widget.combo_box.lineEdit().setText(
            self.unreal_engine_versions_widget.itemData(index).path
        )
        project_path = _evaluate_unreal_project_path(
            self._unreal_project_path_template,
            self.unreal_version,
        ) or ""
        self.unreal_project_widget.set_path(project_path)

    @property
    def unreal_version(self):
        """
        Return the selected Unreal version string.

        :returns: An Unreal version number as a string, or `None`.
        """
        sel = self.unreal_engine_versions_widget.currentIndex()
        if sel != -1:
            return self.unreal_engine_versions_widget.itemData(sel).version
        return None

    @property
    def unreal_path(self):
        """
        Return the current Unreal executable path.

        :returns: A string.
        """
        return self.unreal_engine_widget.get_path()

    @property
    def unreal_project_path(self):
        """
        Return the current Unreal project path.

        :returns: A string.
        """
        return self.unreal_project_widget.get_path()


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
    def icon(self):
        """
        Return the path to this item's icon.

        :returns: Full path to an icon.
        """
        return os.path.join(
            self.disk_location,
            os.path.pardir,
            "icons",
            "unreal.png"
        )

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
        settings = {
            "Publish Template": {
                "type": "template",
                "default": None,
                "description": "Template path for published work files. Should"
                               "correspond to a template defined in "
                               "templates.yml.",
            },
            "Work Template": {
                "type": "template",
                "default": None,
                "description": "Template path for exported FBX files. Should"
                               "correspond to a template defined in "
                               "templates.yml.",
            },
            "Unreal Engine Version": {
                "type": "string",
                "default": "4.26",
                "description": "Version of the Unreal Engine executable to use."
            },
            "Unreal Engine Path": {
                "type": "string",
                "default": None,
                "description": "Full path the Unreal Engine executable to use."
            },
            # TODO: check if this should actually be a TK template.
            "Unreal Project Path Template": {
                "type": "string",
                "default": "{config}/tk-multi-publish2/tk-maya/unreal/resources/{unreal_engine_version}/turntable/turntable.uproject",
                "description": "Path template to the Unreal project to load."
                               "{config}, {engine}, {unreal_engine_version} keys "
                               "can be used and are replaced with runtime values."
            },
            "Unreal Project Path": {
                "type": "string",
                "default": None,
                "description": "Path to the Unreal project to load."
            },
            "Turntable Map Path": {
                "type": "string",
                "default": "/Game/turntable/level/turntable.umap",
                "description": "Unreal path to the turntable map to use to render the turntable."
            },
            "Sequence Path": {
                "type": "string",
                "default": "/Game/turntable/sequence/turntable_sequence.turntable_sequence",
                "description": "Unreal path to the level sequence to use to render the turntable."
            },
            "Turntable Assets Path": {
                "type": "string",
                "default": "/Game/maya_turntable_assets/",  # TODO: make sure the trailing / is not needed.
                "description": "Unreal output path where the turntable assets will be imported."
            },
        }

        # Update the base settings with our settings
        base_settings.update(settings)
        return base_settings

    @property
    def item_filters(self):
        """
        List of item types that this plugin is interested in.

        Only items matching entries in this list will be presented to the
        accept() method. Strings can contain glob patters such as *, for example
        ["maya.*", "file.maya"]
        """
        return ["maya.session.secondaries"]

    def create_settings_widget(self, parent):
        """
        Creates a Qt widget, for the supplied parent widget (a container widget
        on the right side of the publish UI).

        :param parent: The parent to use for the widget being created
        :return: A :class:`QtGui.QFrame` that displays editable widgets for
                 modifying the plugin's settings.
        """
        # defer Qt-related imports
        from sgtk.platform.qt import QtGui

        # Create a QFrame with all our widgets
        settings_frame = QtGui.QFrame(parent)
        # Create our widgets, we add them as properties on the QFrame so we can
        # retrieve them easily. Qt uses camelCase so our xxxx_xxxx names can't
        # clash with existing Qt properties.

        # Show this plugin description
        settings_frame.description_label = QtGui.QLabel(self.description)
        settings_frame.description_label.setWordWrap(True)
        settings_frame.description_label.setOpenExternalLinks(True)

        # Unreal setttings
        settings_frame.unreal_setup_widget = UnrealSetupWidget()
        settings_frame.unreal_turntable_map_label = QtGui.QLabel("Unreal Turntable Map Path:")
        settings_frame.unreal_turntable_map_widget = QtGui.QLineEdit("")

        settings_frame.unreal_sequence_label = QtGui.QLabel("Unreal Sequence Path:")
        settings_frame.unreal_sequence_widget = QtGui.QLineEdit("")

        settings_frame.unreal_turntable_asset_label = QtGui.QLabel("Unreal Turntable Assets Path:")
        settings_frame.unreal_turntable_asset_widget = QtGui.QLineEdit("")


        # Create the layout to use within the QFrame
        settings_layout = QtGui.QVBoxLayout()
        settings_layout.addWidget(settings_frame.description_label)
        settings_layout.addWidget(settings_frame.unreal_setup_widget)
        settings_layout.addWidget(settings_frame.unreal_turntable_map_label)
        settings_layout.addWidget(settings_frame.unreal_turntable_map_widget)
        settings_layout.addWidget(settings_frame.unreal_sequence_label)
        settings_layout.addWidget(settings_frame.unreal_sequence_widget)
        settings_layout.addWidget(settings_frame.unreal_turntable_asset_label)
        settings_layout.addWidget(settings_frame.unreal_turntable_asset_widget)

        settings_layout.addStretch()
        settings_frame.setLayout(settings_layout)
        return settings_frame

    def get_ui_settings(self, widget):
        """
        Method called by the publisher to retrieve setting values from the UI.

        :returns: A dictionary with setting values.
        """
        self.logger.info("Getting settings from UI")
        # Please note that we don't have to return all settings here, just the
        # settings which are editable in the UI.
        settings = {
            "Unreal Engine Version": six.ensure_str(widget.unreal_setup_widget.unreal_version),
            "Unreal Engine Path": six.ensure_str(widget.unreal_setup_widget.unreal_path),
            # Get the project path evaluated from the template or the value which
            # was manually set.
            "Unreal Project Path": six.ensure_str(widget.unreal_setup_widget.unreal_project_path),
            "Turntable Map Path": six.ensure_str(widget.unreal_turntable_map_widget.text()),
            "Sequence Path": six.ensure_str(widget.unreal_sequence_widget.text()),
            "Turntable Assets Path": six.ensure_str(widget.unreal_turntable_asset_widget.text()),
            #"HDR Path": widget.hdr_image_template_widget.get_path(),
            #"Start Frame": widget.start_frame_spin_box.value(),
            #"End Frame": widget.end_frame_spin_box.value(),
        }
        return settings

    def set_ui_settings(self, widget, settings):
        """
        Method called by the publisher to populate the UI with the setting values.

        :param widget: A QFrame we created in `create_settings_widget`.
        :param settings: A list of dictionaries.
        :raises NotImplementedError: if editing multiple items.
        """
        self.logger.info("Setting UI settings")
        if len(settings) > 1:
            # We do not allow editing multiple items
            raise NotImplementedError
        cur_settings = settings[0]
        unreal_versions = self.get_unreal_versions()
        widget.unreal_setup_widget.populate_unreal_versions(
            unreal_versions,
            cur_settings["Unreal Engine Version"],
        )
        widget.unreal_setup_widget.set_unreal_project_path_template(
            cur_settings["Unreal Project Path Template"]
        )
        widget.unreal_turntable_map_widget.setText(cur_settings["Turntable Map Path"])
        widget.unreal_sequence_widget.setText(cur_settings["Sequence Path"])
        widget.unreal_turntable_asset_widget.setText(cur_settings["Turntable Assets Path"])

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

        accepted = True
        publisher = self.parent

        # Ensure a work file template is available on the item
        work_template = item.properties.get("work_template")
        if not work_template:
            self.logger.debug(
                "A work template is required for the session item in order to "
                "publish a turntable.  Not accepting the item."
            )
            accepted = False

        # Ensure the publish template is defined and valid and that we also have
        template_name = settings["Publish Template"].value
        publish_template = publisher.get_template_by_name(template_name)
        if not publish_template:
            self.logger.debug(
                "The valid publish template could not be determined for the "
                "turntable.  Not accepting the item."
            )
            accepted = False

        # we've validated the publish template. add it to the item properties
        # for use in subsequent methods
        item.properties["publish_template"] = publish_template

        # because a publish template is configured, disable context change. This
        # is a temporary measure until the publisher handles context switching
        # natively.
        item.context_change_allowed = False

        self.logger.info("Accepting item %s" % item)
        return {
            "accepted": accepted,
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
        :returns: ``True`` if item is valid, ``False`` otherwise.
        :raises ValueError: For problems which can't be solved in the current session.
        """

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
            return False

        # get the normalized path
        path = sgtk.util.ShotgunPath.normalize(path)

        # get the configured work file template
        work_template = item.properties.get("work_template")
        publish_template = item.properties.get("publish_template")

        # get the current scene path and extract fields from it using the work
        # template:
        work_fields = work_template.get_fields(path)

        # stash the current scene path in properties for use later
        item.properties["work_path"] = path

        # Add additional keys needed by the template
        if sys.platform == "win32":
            work_fields["ue_mov_ext"] = "avi"
        else:
            work_fields["ue_mov_ext"] = "mov"

        # Ensure the fields work for the publish template
        missing_keys = publish_template.missing_keys(work_fields)
        if missing_keys:
            error_msg = "Work file '%s' missing keys required for the " \
                        "publish template: %s" % (path, missing_keys)
            self.logger.error(error_msg)
            return False

        # Validate the Unreal executable and project, stash it in properties
        self.get_unreal_exec_property(settings, item)

        # Check the Unreal project path and store it in properties.
        self.get_unreal_project_property(settings, item)

        # Validate the Unreal data settings, stash in properties
        turntable_map_path = settings["Turntable Map Path"].value
        if not turntable_map_path:
            self.logger.debug("No Unreal turntable map configured.")
            return False
        item.properties["turntable_map_path"] = turntable_map_path

        # Validate the Unreal level sequence path, stash in properties
        sequence_path = settings["Sequence Path"].value
        if not sequence_path:
            self.logger.debug("No Unreal turntable sequence configured.")
            return False
        item.properties["sequence_path"] = sequence_path

        # Validate the Unreal content browser path, stash in properties
        unreal_content_browser_path = settings["Turntable Assets Path"].value
        if not unreal_content_browser_path:
            self.logger.debug("No Unreal turntable assets output path configured.")
            return False
        item.properties["unreal_content_browser_path"] = unreal_content_browser_path

        item.properties["path"] = path
        # Create the publish path by applying the fields. store it in the item's
        # properties. This is the path we'll create and then publish in the base
        # publish plugin. Also set the publish_path to be explicit.
        # NOTE: local_properties is used here as directed in the publisher
        # docs when there may be more than one plugin operating on the
        # same item in order for each plugin to have it's own values that
        # aren't overwritten by the other.
        item.local_properties["publish_path"] = publish_template.apply_fields(work_fields)
        item.local_properties["publish_type"] = "Unreal Turntable Render"

        # use the work file's version number when publishing
        if "version" in work_fields:
            item.properties["publish_version"] = work_fields["version"]

        return True

    def get_unreal_exec_property(self, settings, item):
        """
        Retrieve the Unreal Engine executable and store it as a property on the
        item.

        This can be overridden in deriving hooks if a different logic is needed.
        The `unreal_exec_path` and `unreal_engine_version` properties must be set
        by this method.

        :param settings: Dictionary of Settings. The keys are strings, matching
                         the keys returned in the settings property. The values
                         are `Setting` instances.
        :param item: Item to process
        :raises RuntimeError: If the Unreal Engine path and its version can't be
                              resolved to valid values.
        """
        # Validate the Unreal executable and project, stash in properties
        unreal_exec_path = settings["Unreal Engine Path"].value
        unreal_engine_version = settings["Unreal Engine Version"].value
        if not unreal_exec_path:
            # The path was not explicitely set, either from settings or the UI,
            # compute one from detected Unreal versions and the default version
            # Collect Unreal versions
            unreal_versions = self.get_unreal_versions()
            if not unreal_versions:
                raise RuntimeError(
                    "No Unreal version could be detected on this machine, please "
                    "set explicitely a value in this item's UI."
                )
            unreal_exec_path = None

            for unreal_version in unreal_versions:
                if unreal_version.version == unreal_engine_version:
                    self.logger.info(
                        "Found matching Unreal version %s for %s" % (unreal_version, unreal_engine_version)
                    )
                    unreal_exec_path = unreal_version.path
                    break
            else:
                # Pick the first entry
                self.logger.info(
                    "Couldn't find a matching Unreal version %s, using %s" % (unreal_engine_version, unreal_versions[0])
                )
                unreal_exec_path = unreal_versions[0].path
                unreal_engine_version = unreal_versions[0].version

        if not unreal_exec_path or not os.path.exists(unreal_exec_path):
            raise RuntimeError(
                "Unreal executable not found at %s" % unreal_exec_path
            )

        item.properties["unreal_exec_path"] = unreal_exec_path
        item.properties["unreal_engine_version"] = unreal_engine_version

    def get_unreal_project_property(self, settings, item):
        """
        Retrieve the Unreal project path and store it in the item `unreal_project_path`
        property.

        This can be overridden in deriving hooks if a different logic is needed.
        The `unreal_project_path` property must be set by this method.

        :param settings: Dictionary of Settings. The keys are strings, matching
                         the keys returned in the settings property. The values
                         are `Setting` instances.
        :param item: Item to process
        :raises RuntimeError: If the a valid project path can't be resolved.
        """
        unreal_project_path = settings["Unreal Project Path"].value
        if not unreal_project_path:
            # The path was not explicitely set, either from settings or the UI,
            # compute one from detected Unreal versions and the default version
            unreal_project_path_template = settings["Unreal Project Path Template"].value
            unreal_project_path = _evaluate_unreal_project_path(
                unreal_project_path_template,
                item.properties["unreal_engine_version"],
            )
        if not unreal_project_path:
            raise RuntimeError(
                "Unable to build an Unreal project path from %s with Unreal version %s" % (
                    unreal_project_path_template,
                    unreal_engine_version,
                )
            )
        if not os.path.isfile(unreal_project_path):
            raise RuntimeError(
                "Unreal project not found at %s" % unreal_project_path
            )
        item.properties["unreal_project_path"] = unreal_project_path

    def publish(self, settings, item):
        """
        Executes the publish logic for the given item and settings.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """

        # Get the Unreal settings again
        unreal_exec_path = item.properties["unreal_exec_path"]
        unreal_project_path = item.properties["unreal_project_path"]
        turntable_map_path = item.properties["turntable_map_path"]
        sequence_path = item.properties["sequence_path"]
        unreal_content_browser_path = item.properties["unreal_content_browser_path"]

        # This plugin publishes a turntable movie to Shotgun
        # These are the steps needed to do that

        # =======================
        # 1. Export the Maya scene to FBX
        # The FBX will be exported to a temp folder
        # Another folder can be specified as long as the name has no spaces
        # Spaces are not allowed in command line Unreal Python args
        temp_folder = tempfile.mkdtemp(suffix="temp_unreal_shotgun")
        # Store the temp folder path on the item for cleanup in finalize
        item.local_properties["temp_folder"] = temp_folder
        fbx_folder = temp_folder

        # Get the filename from the work file
        # TODO: double check but it seems path could be used here?
        work_path = item.properties.get("work_path")
        work_path = os.path.normpath(work_path)
        work_name = os.path.splitext(os.path.basename(work_path))[0]

        # Replace non-word characters in filename, Unreal doesn't like those
        # Substitute '_' instead
        exp = re.compile(r"\W", re.UNICODE)
        work_name = exp.sub("_", work_name)

        # Use current time as string as a unique identifier
        now = datetime.datetime.now()
        timestamp = str(now.hour) + str(now.minute) + str(now.second)

        # Replace file extension with .fbx and suffix it with "_turntable"
        fbx_name = work_name + "_" + timestamp + "_turntable.fbx"
        fbx_output_path = os.path.join(fbx_folder, fbx_name)
        
        # Export the FBX to the given output path
        if not self._maya_export_fbx(fbx_output_path):
            return False

        # Keep the fbx path for cleanup at finalize
        item.properties["temp_fbx_path"] = fbx_output_path
        
        # =======================
        # 2. Import the FBX into Unreal.
        # 3. Instantiate the imported asset into a duplicate of the turntable map.
        # Use the unreal_setup_turntable to do this in Unreal

        current_folder = os.path.dirname( __file__ )
        script_path = os.path.abspath(
            os.path.join(
                current_folder,
                os.path.pardir,
                "unreal",
                "unreal_setup_turntable.py"
            )
        )

        # Workaround for script path with spaces in it
        if " " in script_path:
            # Make temporary copies of the scripts to a path without spaces
            script_destination = os.path.join(self.temp_folder, "unreal_setup_turntable.py")
            shutil.copy(script_path, script_destination)
            script_path = script_destination

            importer_path = os.path.abspath(
                os.path.join(
                    current_folder,
                    os.path.pardir,
                    "unreal",
                    "unreal_importer.py",
                )
            )
            importer_destination = os.path.join(self.temp_folder, "unreal_importer.py")
            shutil.copy(importer_path, importer_destination)

        if " " in unreal_project_path:
            unreal_project_path = '"{}"'.format(unreal_project_path)
            
        # Set the script arguments in the environment variables            
        # The FBX to import into Unreal
        os.environ[OUTPUT_PATH_ENVVAR] = fbx_output_path
        self.logger.info("Setting environment variable {} to {}".format(OUTPUT_PATH_ENVVAR, fbx_output_path))

        # The Unreal content browser folder where the asset will be imported into
        os.environ[CONTENT_BROWSER_PATH_ENVVAR] = unreal_content_browser_path
        self.logger.info("Setting environment variable {} to {}".format(CONTENT_BROWSER_PATH_ENVVAR, unreal_content_browser_path))

        # The Unreal turntable map to duplicate where the asset will be instantiated into
        os.environ[MAP_PATH_ENVVAR] = turntable_map_path
        self.logger.info("Setting environment variable {} to {}".format(MAP_PATH_ENVVAR, turntable_map_path))

        self._unreal_execute_script(
            unreal_exec_path,
            unreal_project_path,
            script_path
        )

        del os.environ[OUTPUT_PATH_ENVVAR]
        del os.environ[CONTENT_BROWSER_PATH_ENVVAR]
        del os.environ[MAP_PATH_ENVVAR]

        # =======================
        # 4. Render the turntable to movie.
        # Output the movie to the publish path
        publish_path = self.get_publish_path(settings, item)
        publish_path = os.path.normpath(publish_path)

        # Split the destination path into folder and filename
        destination_folder = os.path.split(publish_path)[0]
        movie_name = os.path.split(publish_path)[1]
        movie_name = os.path.splitext(movie_name)[0]

        # Ensure that the destination path exists before rendering the sequence
        self.parent.ensure_folder_exists(destination_folder)
        self.logger.info("Rendering turntable to %s" % publish_path)
        # Render the turntable
        self._unreal_render_sequence_to_movie(
            unreal_exec_path,
            unreal_project_path,
            turntable_map_path,
            sequence_path,
            destination_folder,
            movie_name
        )
        if not os.path.isfile(publish_path):
            raise RuntimeError(
                "Expected file %s was not generated" % publish_path
            )
        # Publish the movie file to Shotgun
        super(MayaUnrealTurntablePublishPlugin, self).publish(settings, item)
        # Save publish data locally on the item to be able to restore it later
        item.local_properties["sg_publish_data"] = item.properties.sg_publish_data

        # Create a Version entry linked with the new publish
        publish_name = item.properties.get("publish_name")
        
        # Populate the version data to send to SG
        self.logger.info("Creating Version...")
        version_data = {
            "project": item.context.project,
            "code": movie_name,
            "description": item.description,
            "entity": self._get_version_entity(item),
            "sg_path_to_movie": publish_path,
            "sg_task": item.context.task,
            "published_files": [item.properties.sg_publish_data],
        }
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
        item.local_properties["sg_version_data"] = version

        # Ensure the path is utf-8 encoded to avoid issues with
        # the shotgun api
        upload_path = six.ensure_text(
            item.properties.sg_publish_data["path"]["local_path"]
        )

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

        # The base implementation needs a property, not a local property
        item.properties.sg_publish_data = item.local_properties.sg_publish_data
        # do the base class finalization
        super(MayaUnrealTurntablePublishPlugin, self).finalize(settings, item)

        # bump the session file to the next version
        # self._save_to_next_version(item.properties["maya_path"], item, _save_session)
        
        # Delete the exported FBX and scripts from the temp folder
        temp_folder = item.local_properties.get("temp_folder")
        if temp_folder:
            shutil.rmtree(temp_folder)

        # Revive this when Unreal supports spaces in command line Python args
        # fbx_path = item.properties.get("temp_fbx_path")
        # if fbx_path:
        #     try:
        #         os.remove(fbx_path)
        #     except:
        #         pass

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
            # Mel script equivalent:
            # import maya.mel as mel
            # mel.eval('FBXExport -f "fbx_output_path"')
            cmds.FBXExport('-f', fbx_output_path)
        except:
            self.logger.error("Could not export scene to FBX")
            return False
            
        return True
        
    def _unreal_execute_script(self, unreal_exec_path, unreal_project_path, script_path):
        """
        """
        command_args = []
        if sys.platform == "darwin" and os.path.splitext(unreal_exec_path)[1] == ".app":
            # Special case for Osx if the Unreal.app was chosen instead of the
            # executable
            command_args = [
                "open",
                "-W",
                "-n",
                "-a",
                unreal_exec_path,  # Unreal executable path
                "--args",
                unreal_project_path,  # Unreal project
                '-ExecutePythonScript="{}"'.format(script_path)  # Script to run in Unreal
            ]
        else:
            command_args = [
                unreal_exec_path,  # Unreal executable path
                unreal_project_path,  # Unreal project
                '-ExecutePythonScript="{}"'.format(script_path)  # Script to run in Unreal
            ]
        self.logger.info(
            "Executing script in Unreal with arguments: {}".format(command_args)
        )
        subprocess.call(command_args)

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
        # Sequencer can only render to avi file format on Windows
        if sys.platform == "win32":
            output_filename = "{}.avi".format(movie_name)
        else:
            # Use .mov for other platforms
            output_filename = "{}.mov".format(movie_name)
        output_filepath = os.path.join(destination_path, output_filename)

        if os.path.isfile(output_filepath):
            # Must delete it first, otherwise the Sequencer will add a number in the filename
            try:
                os.remove(output_filepath)
            except OSError as e:
                self.logger.debug("Couldn't delete {}. The Sequencer won't be able to output the movie to that file.".format(output_filepath))
                return False, None

        # Render the sequence to a movie file using the following command-line arguments
        cmdline_args = []
        
        # Note that any command-line arguments (usually paths) that could contain spaces must be enclosed between quotes

        if sys.platform == "darwin" and os.path.splitext(unreal_exec_path)[1] == ".app":
            # Special case for Osx if the Unreal.app was chosen instead of the
            # executable
            cmdline_args = [
                "open",
                "-W",
                "-n",
                "-a",
                unreal_exec_path,  # Unreal executable path
                "--args",
                unreal_project_path,  # Unreal project
                unreal_map_path,  # Level to load for rendering the sequence
            ]
        else:
            cmdline_args = [
                unreal_exec_path,  # Unreal executable path
                unreal_project_path,  # Unreal project
                unreal_map_path,  # Level to load for rendering the sequence
            ]

        # Command-line arguments for Sequencer Render to Movie
        # See: https://docs.unrealengine.com/en-us/Engine/Sequencer/Workflow/RenderingCmdLine
        cmdline_args.extend([
            "-LevelSequence={}".format(sequence_path),  # The sequence to render
            '-MovieFolder="{}"'.format(destination_path),  # Output folder, must match the work template
            "-MovieName={}".format(movie_name),  # Output filename
            "-game",
            "-MovieSceneCaptureType=/Script/MovieSceneCapture.AutomatedLevelSequenceCapture",
            "-ResX=1280",
            "-ResY=720",
            "-ForceRes",
            "-Windowed",
            "-MovieCinematicMode=yes",
            "-MovieFormat=Video",
            "-MovieFrameRate=24",
            "-MovieQuality=75",
            "-MovieWarmUpFrames=30",
            "-NoTextureStreaming",
            "-NoLoadingScreen",
            "-NoScreenMessages",
        ])
        self.logger.info("Sequencer command-line arguments: {}".format(cmdline_args))
        
        # TODO: fix command line arguments which contain space.
        subprocess.call(cmdline_args)

        return os.path.isfile(output_filepath), output_filepath

    def get_unreal_versions(self):
        """
        Return a list of all known Unreal versions installed locally.

        Uses the Engine Launcher logic to scan for Unreal executables and selects the one that
        matches the version defined in the settings, prioritizing non-development builds

        :returns: A list of TK software versions.
        """

        # Create a launcher for the current context
        engine = sgtk.platform.current_engine()
        software_launcher = sgtk.platform.create_engine_launcher(engine.sgtk, engine.context, "tk-unreal")

        # Discover which versions of Unreal are available
        software_versions = software_launcher.scan_software()
        versions = []
        dev_versions = []
        for software_version in software_versions:
            # Insert non-dev builds at the start of the list
            if "(Dev Build)" not in software_version.display_name:
                versions.append(software_version)
            else:
                dev_versions.append(software_version)
        fake_versions = []
# Can be uncommented to fake multiple SW versions if needed.
#        fake_versions = [
#            SoftwareVersion(
#                "Faked 5",
#                "Faked",
#                "faked"
#            ),
#            SoftwareVersion(
#                "Faked 6",
#                "Faked",
#                "faked"
#            )
#
#        ]
        return fake_versions + versions + dev_versions
            
        return None

def _evaluate_unreal_project_path(unreal_project_path_template, unreal_engine_version):
    """
    Return the path to the Unreal project to use based on the given template and
    Unreal version.

    It uses the same path resolution as for hook paths to expand {config} and {engine}
    to their absolute path equivalent.

    .. note :: The project template is not a regular TK template but a string
               with {config}, {engine} and {unreal_engine_version} which are replaced.

    :param str unreal_project_path_template: A path template to use to resolve the
                                             the project path.
    :param str unreal_engine_version: An Unreal version number as a string.
    :returns: An absolute path to the Unreal project to use, or `None`.
    """
    if not unreal_project_path_template:
        return None

    if not unreal_engine_version:
        return None
    # Only keep major.minor from the Unreal version
    short_version = ".".join(unreal_engine_version.split(".")[:2])
    # Evaluate the "template"
    engine = sgtk.platform.current_engine()
    hooks_folder = engine.sgtk.pipeline_configuration.get_hooks_location()
    engine_hooks_path = os.path.join(engine.disk_location, "hooks")
    return os.path.normpath(
        unreal_project_path_template.replace(
            "{config}",
            hooks_folder
        ).replace(
            "{engine}",
            engine_hooks_path
        ).replace(
            "{unreal_engine_version}",
            short_version
        )
    )

def _session_path():
    """
    Return the path to the current session
    :return:
    """
    path = cmds.file(query=True, sn=True)

    return six.ensure_text(path)


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
