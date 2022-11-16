[![Build Status](https://dev.azure.com/shotgun-ecosystem/Toolkit/_apis/build/status/Configs/tk-config-default2?branchName=master)](https://dev.azure.com/shotgun-ecosystem/Toolkit/_build/latest?definitionId=49&branchName=master)

-------------------------------------------------------------------------
Configuration for running ShotGrid with the Unreal Engine
-------------------------------------------------------------------------

This Toolkit configuration was forked from [tk-config-default2](https://github.com/shotgunsoftware/tk-config-default2) and updates
from that configuration are regularly merged in.

This configuration extends the tk-config-default2 configuration with an 
Unreal engine as well as several unreal related options in Maya.

For more information how to use the unreal engine, please see the support
documentation:

https://docs.unrealengine.com/5.0/en-US/using-unreal-engine-with-autodesk-shotgrid/

For more information about ShotGrid integrations, go to the following url:
https://developer.shotgridsoftware.com/8085533c/?title=ShotGrid+Integrations+Admin+Guide


## Updating this config with changes from the ShotGrid default2 config

It is possible to update this config with latest changes done on the ShotGrid default2 config, for example
to update ShotGrid Toolkit standard apps to their latest approved version.

This can be done by merging a particular ShotGrid default2 config into a branch and merging this branch once checked on master

* Add ShotGrid default2 config repo as a remote:  `git remote add sgdefault2 git@github.com:shotgunsoftware/tk-config-default2.git`
* Fetch latest changes for the ShotGrid default2 config repo:  `git fetch sgdefault2 master`
* You can checkout these changes in a branch to check logs and tags:  `git checkout sgdefault2/master`
* If needed you can keep this branch around with: `git switch -c sgmaster`
* Create a new merge branch from the master branch: `git checkout -b default2_merge`
* Merge a particular tag on this branch: `git merge v1.3.11`.
* A regular merge needs to be used to preserve tags from the ShotGrid default2 config.
* Fix conflicts if any, commit and review changes.
* Merge approved changes on master, tag the internal release, push changes and the tags: `git push; git push --tags`.

The convention used so far when tagging releases for this config is `<ShotGrid default2 config release>-unreal.<internal release>` 
For example `v1.3.11-unreal.0.2.6`

-------------------------------------------------------------------------
