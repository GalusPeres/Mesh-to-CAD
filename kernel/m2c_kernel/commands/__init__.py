"""Protocol commands, one module per method group (the module name is the group).

Every public function decorated with `@command` is a protocol method. Codegen
turns the modules into `src/shared/protocol/generated/<group>.ts`.
"""
