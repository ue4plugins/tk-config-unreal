# Setup the asset in the turntable level for rendering

import unreal
import os
import sys

def main(argv):
    # Import the FBX into Unreal using the unreal_importer script
    current_folder = os.path.dirname( __file__ )
    
    if current_folder not in sys.path:
        sys.path.append(current_folder)

    import unreal_importer

    unreal_importer.main(argv[0:2])

    fbx_file_path = argv[0]
    content_browser_path = argv[1]
    turntable_map_path = argv[2]

    # Duplicate the turntable template map
    world = unreal.EditorLoadingAndSavingUtils.new_map_from_template(turntable_map_path, False)
    
    if not world:
        return
    
    # Derive the imported asset path from the given FBX filename and content browser path
    fbx_filename = os.path.basename(fbx_file_path)
    asset_name = os.path.splitext(fbx_filename)[0]
    asset_path_to_load =  content_browser_path + asset_name
    
    # Load the asset to spawn it at origin
    asset = unreal.EditorAssetLibrary.load_asset(asset_path_to_load)
    if not asset:
        return
        
    unreal.EditorLevelLibrary.spawn_actor_from_object(asset, unreal.Vector.ZERO_VECTOR)
    
    # Save the duplicated map (can't have the same name for the static mesh asset and the map)
    new_map_filename = content_browser_path + asset_name + "_level"
    unreal.EditorLoadingAndSavingUtils.save_map(world, new_map_filename)
    
if __name__ == "__main__":
    # Script arguments must be, in order:
    # Path to FBX to import
    # Unreal content browser path where to store the imported asset
    # Unreal content browser path to the turntable map to duplicate and where to spawn the asset
    main(sys.argv[1:])
