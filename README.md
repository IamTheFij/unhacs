# unhacs

A command line alternative to the "Home Assistant Community Store", aka HACS

## Installation

```bash
pipx install unhacs
```

## Usage

Unhacs provides several commands to manage your Home Assistant packages:

### Add a package

To add a package, use the `add` command followed by the URL of the package. Optionally, you can specify the package name and version:

```bash
unhacs add --url <package_url> --name <package_name> --version <version>
```

If the package already exists, you can update it by adding the `--update` flag:

```bash
unhacs add --url <package_url> --update
```

### List packages

To list all installed packages, use the `list` command:

```bash
unhacs list
```

For a more detailed output, add the `--verbose` flag:

```bash
unhacs list --verbose
```

### Remove a package

To remove a package, use the `remove` command followed by the name of the package:

```bash
unhacs remove <package_name>
```

### Upgrade packages

To upgrade all packages, use the `upgrade` command:

```bash
unhacs upgrade
```

To upgrade specific packages, add their names after the `upgrade` command:

```bash
unhacs upgrade <package_name_1> <package_name_2> ...
```

## License

Unhacs is licensed under the MIT License. See the LICENSE file for more details.

## Original repo

Originally hosted at https://git.iamthefij.com/iamthefij/unhacs.git
