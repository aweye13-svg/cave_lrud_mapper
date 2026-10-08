def classFactory(iface):
    from .cave_mapper import CaveLRUDPlugin
    return CaveLRUDPlugin(iface)