# unhacs

A command line alternative to the "Home Assistant Community Store", aka HACS

## Installation

```bash
pipx install unhacs
```

## Usage

Unhacs provides several commands to manage your Home Assistant packages. It stores installed or requsted packages in a lock file called `unhacs.yaml`. This makes it possible to version control your packages and easily share them with others.

### Add a package

To add a package, use the `add` command followed by the URL of the package. Optionally, you can specify the package name and version. If no version is specified, the latest version will be installed:

```bash
unhacs add <package_url>
unhacs add <package_url> --version <version>
```

If the package already exists, you can update it by adding the `--update` flag:

```bash
unhacs add <package_url> --update
```

If the package is a Lovelace plugins or theme, install it using the appropriate flags:

```bash
unhacs add --plugin <package_url>
unhacs add --theme <package_url>
```

If you already have a list of packages in a file, you can add them all at once using the `--file` flag:

```bash
unhacs add --file ./unhacs.yaml
```

#### Add a component from a forked Home Assistant Core repository

To add a component from a fork of home-assistant/core, use the `--fork-component` flag followed by the name ofthe component and then specify the branch with the `--fork-branch` flag:

```bash
unhacs add --fork-component <component_name> --fork-branch <branch_name> <forked_repo_url>
```

### List packages

To list all installed packages, use the `list` command:

```bash
unhacs list
unhacs list --verbose
```

### List tags

To list all tags for a package, use the `tags` command followed by the name of the package:

```bash
unhacs tags <package_url>
unhacs tags <package_url> --limit 20
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

## Use git tags

By default, identification of releases uses the GitHub API. If you want to use git tags instead, you can add the `--git-tags` flag to the base command:

```bash
unhacs --git-tags add <package_url>
```

## License

Unhacs is licensed under the MIT License. See the LICENSE file for more details.

## Original repo

Originally hosted at https://git.iamthefij.com/iamthefij/unhacs.git
