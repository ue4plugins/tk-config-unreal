# Copyright 2018 Epic Games, Inc. 

# Setup the asset in the turntable level for rendering

import unreal
import os
import sys


def setup_render_with_movie_render_queue(output_path, unreal_map_path, sequence_path):
    """
    Setup rendering the given map and sequence to the given movie with the Movie render queue.

    :param str output_path: Full path to the movie to render.
    :param str unreal_map_path: Unreal map path.
    :param str sequence_path: Unreal level sequence path.
    :returns: Full path to a manifest file to use for rendering or None if rendering
              with the Movie Render queue is not possible.
    """
    # Check if we can use the Movie render queue, bail out if we can't
    if "MoviePipelineQueueEngineSubsystem" not in dir(unreal):
        unreal.log(
            "Movie Render Queue is not available, Movie queue rendering can't be setup."
        )
        return None
    if "MoviePipelineAppleProResOutput" not in dir(unreal):
        unreal.log(
            "Apple ProRes Media plugin must be loaded to be able to render with the Movie Render Queue, "
            "Movie queue rendering can't be setup."
        )
        return None

    unreal.log("Setting rendering %s %s to %s..." % (unreal_map_path, sequence_path, output_path))
    output_folder, output_file = os.path.split(output_path)
    movie_name = os.path.splitext(output_file)[0]

    qsub = unreal.MoviePipelineQueueEngineSubsystem()
    queue = qsub.get_queue()
    job = queue.allocate_new_job(unreal.MoviePipelineExecutorJob)
    job.sequence = unreal.SoftObjectPath(sequence_path)
    job.map =  unreal.SoftObjectPath(unreal_map_path)
    # Set settings
    config = job.get_configuration()
    output_setting = config.find_or_add_setting_by_class(unreal.MoviePipelineOutputSetting)
    # https://docs.unrealengine.com/4.26/en-US/PythonAPI/class/MoviePipelineOutputSetting.html?highlight=setting#unreal.MoviePipelineOutputSetting
    output_setting.output_directory =  unreal.DirectoryPath(output_folder)
    output_setting.output_resolution = unreal.IntPoint(1280, 720)
    output_setting.file_name_format = movie_name
    output_setting.override_existing_output = True  # Overwrite existing files
    # Render to a movie
    mov_setting = config.find_or_add_setting_by_class(unreal.MoviePipelineAppleProResOutput)
    # TODO: check which codec we should use.
    # Default rendering
    render_pass = config.find_or_add_setting_by_class(unreal.MoviePipelineDeferredPassBase)
    # Additional pass with detailed lighting?
    # render_pass = config.find_or_add_setting_by_class(unreal.MoviePipelineDeferredPass_DetailLighting)
    _, manifest_path = unreal.MoviePipelineEditorLibrary.save_queue_to_manifest_file(queue)
    unreal.log("Saved rendering manifest to %s" % manifest_path)
    return manifest_path

def setup_turntable(fbx_file_path, assets_path, turntable_map_path):
    """
    Setup the turntable project to render the given FBX file.

    :param str fbx_file_path: Full path to the FBX file to import and render.
    :param str assets_path: Unreal path under which the FBX file should be imported.
    :param str turntable_map_path: Unreal map path.
    :returns: The loaded map path.
    """
    # Import the FBX into Unreal using the unreal_importer script
    current_folder = os.path.dirname(__file__)
    
    if current_folder not in sys.path:
        sys.path.append(current_folder)
    # TODO: check if there is any reason to keep this in another .py file
    # instead of having it just here.
    import unreal_importer

    unreal.log("Importing FBX file %s under %s..." % (fbx_file_path, assets_path))
    unreal_importer.import_fbx(fbx_file_path, assets_path)

    unreal.log("Loading map %s..." % turntable_map_path)
    # Load the turntable map where to instantiate the imported asset
    world = unreal.EditorLoadingAndSavingUtils.load_map(turntable_map_path)
    
    if not world:
        unreal.error("Unable to load map %s" % turntable_map_path)
        return
    unreal.log("Setting up turntable actor...")
    # Find the turntable actor, which is used in the turntable sequence that rotates it 360 degrees
    turntable_actor = None
    level_actors = unreal.EditorLevelLibrary.get_all_level_actors()
    for level_actor in level_actors:
        if level_actor.get_actor_label() == "turntable":
            turntable_actor = level_actor
            break
            
    if not turntable_actor:
        return
        
    # Destroy any actors attached to the turntable (attached for a previous render)
    for attached_actor in turntable_actor.get_attached_actors():
        unreal.EditorLevelLibrary.destroy_actor(attached_actor)
        
    # Derive the imported asset path from the given FBX filename and content browser path
    fbx_filename = os.path.basename(fbx_file_path)
    asset_name = os.path.splitext(fbx_filename)[0]
    # The path here is not a file path, it is an Unreal path so '/' is always used.
    asset_path_to_load =  "%s/%s" % (assets_path, asset_name)
    
    # Load the asset to spawn it at origin
    asset = unreal.EditorAssetLibrary.load_asset(asset_path_to_load)
    if not asset:
        return
        
    actor = unreal.EditorLevelLibrary.spawn_actor_from_object(asset, unreal.Vector(0, 0, 0))
    
    # Scale the actor to fit the frame, which is dependent on the settings of the camera used in the turntable sequence
    # The scale values are based on a volume that fits safely in the frustum of the camera and account for the frame ratio
    # and must be tweaked if the camera settings change
    origin, bounds = actor.get_actor_bounds(True)
    scale_x = 250 / min(bounds.x, bounds.y)
    scale_y = 300 / max(bounds.x, bounds.y)
    scale_z = 200 / bounds.z
    scale = min(scale_x, scale_y, scale_z)
    actor.set_actor_scale3d(unreal.Vector(scale, scale, scale))
    
    # Offset the actor location so that it rotates around its center
    origin = origin * scale
    actor.set_actor_location(unreal.Vector(-origin.x, -origin.y, -origin.z), False, True)
    
    # Attach the newly spawned actor to the turntable
    actor.attach_to_actor(turntable_actor, "", unreal.AttachmentRule.KEEP_WORLD, unreal.AttachmentRule.KEEP_WORLD, unreal.AttachmentRule.KEEP_WORLD, False)

    unreal.log("Saving current level...")
    unreal.EditorLevelLibrary.save_current_level()
    unreal.log("Saving map %s" % world.get_path_name())
    # This seems to fail with:
    # [2021.09.15-15.17.52:220][  1]Message dialog closed, result: Ok, title: Message, text: Failed to save the map. The filename '../../../../../../../var/folders/rt/vlgl5dzj75q2qg4t9fp9gfx80000gp/T/tmpO8A5Lw/turntable/Content/turntable/level/turntable.turntable.umap' is not within the game or engine content folders found in '/Users/Shared/Epic Games/UE_4.26/'.
    unreal.EditorLoadingAndSavingUtils.save_map(world, world.get_path_name())
    unreal.log("Turntable setup done.")
    return world.get_path_name()

if __name__ == "__main__":
    # Script arguments must be, in order:
    # Path to FBX to import
    # Unreal content browser path where to store the imported asset
    # Unreal content browser path to the turntable map to duplicate and where to spawn the asset
    # Retrieve arguments from the environment
    fbx_file_path = os.environ["UNREAL_SG_FBX_OUTPUT_PATH"]
    assets_path = os.environ["UNREAL_SG_ASSETS_PATH"]
    turntable_map_path = os.environ["UNREAL_SG_MAP_PATH"]

    # Additional settings to render with the Movie Render Queue
    movie_path = os.environ.get("UNREAL_SG_MOVIE_OUTPUT_PATH")
    level_sequence_path = os.environ.get("UNREAL_SG_SEQUENCE_PATH")

    map_path = setup_turntable(fbx_file_path, assets_path, turntable_map_path)

    if movie_path and level_sequence_path:
        setup_render_with_movie_render_queue(
            movie_path,
            map_path,
            level_sequence_path,
        )
