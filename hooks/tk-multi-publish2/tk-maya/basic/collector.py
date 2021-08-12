# This file is based on templates provided and copyrighted by Autodesk, Inc.
# This file has been modified by Epic Games, Inc. and is subject to the license
# file included in this repository.

import sgtk


HookBaseClass = sgtk.get_hook_baseclass()


class MayaSessionCollectorWithSecondaries(HookBaseClass):
    """
    Collector that operates on the Maya session.

    Extend the base implementation to add some items under the `session` item.

    This hook relies on functionality found in the Maya collector hook in
    the tk-maya Engine and should inherit from it in the configuration.
    The setting for this plugin should look something like this:

        collector: "{self}/collector.py:{engine}/tk-multi-publish2/basic/collector.py:{config}/tk-multi-publish2/tk-maya/basic/collector.py"
    """


    def collect_current_maya_session(self, settings, parent_item):
        """
        Creates an item that represents the current maya session.

        Override base implementation to add a "secondaries" item under the session item.
        This item can be used to export and publish the current Maya scene
        to different file formats.

        :param parent_item: Parent Item instance
        :returns: Item of type maya.session
        """
        session_item = super(MayaSessionCollectorWithSecondaries, self).collect_current_maya_session(settings, parent_item)
        secondaries_item = session_item.create_item(
            "maya.session.secondaries",
            "Secondary actions",
            "Additional Items"
        )
        # Copy the work template from the session item to the secondaries item
        # so base publish hooks which rely on it can be used.
        work_template = session_item.properties.get("work_template")
        if work_template:
            secondaries_item.properties["work_template"] = work_template

        return session_item
