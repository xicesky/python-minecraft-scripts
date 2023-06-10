from pkg_resources import resource_string, resource_listdir
import yaml


def deep_merge(value1, value2):
    if isinstance(value1, dict) and isinstance(value2, dict):
        return ConfigDict(**{k: deep_merge_key(value1, value2, k) for k in set(value1) | set(value2)})
    return value2


def deep_merge_key(dict1, dict2, key):
    if key in dict1:
        if key in dict2:
            return deep_merge(dict1[key], dict2[key])
        return dict1[key]
    return dict2[key]


class ConfigDict(dict):
    """ A dictionary that can be used as a configuration
    Can be (deeply) merged with other dictionaries
    """
    yaml_loader = yaml.SafeLoader

    def __init__(self, **kw) -> None:
        super().__init__(**kw)

    def __repr__(self) -> str:
        return super().__repr__()

    def __str__(self) -> str:
        return super().__str__()

    def __getattr__(self, name):
        return self[name]

    def __setattr__(self, name, value):
        self[name] = value

    def __delattr__(self, name):
        del self[name]

    # Override all the default dict operations to return a ConfigDict
    # override merging operations to merge the values instead of replacing them

    def __getitem__(self, key):
        value = super().__getitem__(key)
        if isinstance(value, dict):
            cd = ConfigDict(**value)
            super().__setitem__(key, cd)
            return cd
        else:
            return value

    def __setitem__(self, key, value):
        if isinstance(value, dict):
            super().__setitem__(key, ConfigDict(**value))
        else:
            super().__setitem__(key, value)

    def __add__(self, other : dict) -> None:
        return deep_merge(self, other)

    def __or__(self, other : dict) -> None:
        return deep_merge(self, other)

    # Actual implementations...

    def to_dict(self):
        return {k: v.to_dict() if isinstance(v, ConfigDict) else v for k, v in self.items()}

    def merge(self, other : dict) -> None:
        return self | other

    def to_yaml(self):
        return yaml.dump(self.to_dict(), default_flow_style=False)

    @staticmethod
    def load_from_yaml_string(string):
        return ConfigDict(**yaml.safe_load(string))

    @staticmethod
    def load_from_yaml_file(filename):
        stream = open(filename, 'r')
        return ConfigDict(**yaml.safe_load(stream))

    @staticmethod
    def load_from_yaml_resource(package_or_requirement, resource_name):
        bytes = resource_string(
            package_or_requirement=package_or_requirement,
            resource_name=resource_name
        )
        return ConfigDict.load_from_yaml_string(bytes.decode('utf-8'))

    @staticmethod
    def default_config():
        return ConfigDict.load_from_yaml_resource('minecraft.serverwrapper', 'default-config.yaml')


def get_default_config_string():
    return resource_string('minecraft.serverwrapper', 'default-config.yaml').decode('utf-8')

if __name__ == '__main__':
    # print(resource_listdir('minecraft.serverwrapper', '.'))
    default_config = ConfigDict.default_config()
    config = default_config | ConfigDict.load_from_yaml_resource('minecraft.serverwrapper', 'example-config.yaml')
    print(type(default_config))
    print(type(config))
    print(config)
    print(config.to_yaml())
