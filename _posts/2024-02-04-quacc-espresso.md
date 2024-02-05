---
layout: post
title: Use the Quantum Accelerator to improve your DFT calculations
date: 2024-02-04 21:00:00
description: I recently discovered Quacc and I implemented an interface for the Quantum Espresso code. Let's try it!
tags: Quacc DFT Espresso ASE
featured: true
---

Not long ago, I was looking at the [Atomic Simulation Environment](https://wiki.fysik.dtu.dk/ase/) (ASE) [ecosystem page](https://wiki.fysik.dtu.dk/ase/ecosystem.html), when I noticed a new contender: The Quantum Accelerator (Quacc) from the [Rosen group](https://rosen.cbe.princeton.edu) at Princeton. It is a new Python package that aims to connect computational chemistry codes to various workflow engines. I quickly got hooked and tried to use it for my work. The package runs around the Atomic Simulation Environment (ASE) and provides recipes and presets to run calculations with ease. You don't necessarily have to use a workflow engine to use it, this tutorial will not use any. [The installation](https://quantum-accelerators.github.io/quacc/install/install.html#installing-quacc) is pretty standard, the only important thing is that you will need the latest ASE version from git before installing it.

Unfortunately, at the time there was no implementation for Quantum Espresso, I did my own and merged it to the main repository. If you know how to use the ASE Espresso interface, Quacc will not be difficult to get your head around.

### Espresso tutorial

Before running everything, Quacc has a configuration file that you must setup correctly to run Espresso calculations. Two important things to set are the path to the Espresso binary and the pseudopotential directory. This configuration file is by default located at `~/.quacc.yaml`. Let's use the CLI to set it up:

```bash
# Setting ESPRESSO_BIN_DIR is not needed if pw.x is in your PATH
quacc set ESPRESSO_BIN_DIR /path/to/espresso/bin
quacc set ESPRESSO_PSEUDO /path/to/espresso/pseudopotentials
```

If you open the configuration file you should notice the changes. For the purpose of this tutorial, you will need to set the `ESPRESSO_PSEUDO` setting to a folder that contains the full [SSSP 1.3.0 efficiency](https://www.materialscloud.org/discover/sssp/table/efficiency) pseudopotential library.

Now, let's try to run a simple calculation. Quacc contains recipes and everything is done under the hood, no need for you to write input files. Let's try to run a simple calculation for a bulk system.

```python
from ase.build import bulk
from quacc.recipes.espresso.core import static_job

atoms = bulk("Si")

results = static_job(atoms)
```

**That's it! You just ran a DFT calculation!**

---
##### **Where are the results?**

Results are stored in the variable `results` which is a dictionary.

- ```results["atoms"]``` contains the final ASE Atoms object.
- ```results["results"]``` contains results from the ASE calculator, such as the energy, forces...
- ```results["input_atoms"]``` contains information about atoms sent to the job.
- ```results["dir_name"]``` contains the directory where the calculation was ran.

There are other keys in the dictionary, but these are the most important ones. Printing the dictionary will give you a better idea of what's inside.

For files, you will notice Quacc creating folders in the current working directory. Calculations are run in temporary folders and at the end files are moved and gzipped to a permanent folder. If this behaviour seems strange, it makes more sense when you consider the use of workflow engines. Settings are available to change the default behaviour; if you want more information about directory management, the Quacc documentation has a nice [page](https://quantum-accelerators.github.io/quacc/user/settings/file_management.html) about it.

---
##### **How do I change the Espresso keywords?**

The static_job is pretty much a wrapper around the ASE Espresso calculator for this purpose. You can pass any parameter that you would pass to the Espresso calculator. Here are some examples:

```python
# input_data in flat dictionary format
static_job(atoms, input_data = {"ecutwfc": 40}, kpts = (4, 4, 4))
# input_data in nested dictionary format, kspacing in units of 1/Å
static_job(atoms, input_data = {"system": {"ecutwfc": 40}}, kspacing = 0.1)
```

---
##### **What are the static_job parameters?**

Let's look at the static_job signature:

```python
@job
def static_job(
    atoms: Atoms,
    preset: str | None = "sssp_1.3.0_pbe_efficiency",
    parallel_info: dict[str] | None = None,
    test_run: bool = False,
    copy_files: str | Path | list[str | Path] | None = None,
    **calc_kwargs,
) -> RunSchema:
```

The preset parameter is the one that defines the pseudopotentials here, it is doing so by looking at a yaml file located in the `ESPRESSO_PRESET` directory. By default, this directory is located inside the Quacc package and no further setup is required. The custom Espresso calculator will look at the recommended cutoff for the elements in the calculation and take the highest one automatically. Preset files for Espresso can be browsed on the [Quacc github](https://github.com/Quantum-Accelerators/quacc/tree/main/src/quacc/calculators/espresso/presets). You will notice the existence of other presets such as "esm_metal_slab_efficiency.yaml" or "tough_metal_clusters_efficiency.yaml" which additionally change the `input_data`. **Of course, any parameters manually passed that conflict with the preset will override it**. If presets are not of interest to you, just set it to `None`.

Let's look at the other parameters, the `parallel_info` parameter is used to define the parallelization settings, ASE style. The `test_run` parameter is used to run a test calculation, it will create a "pwscf.EXIT" file which instructs pw.x to perform a dry-run, useful for checking that your input does not contain any errors. The `copy_files` parameter is used to copy files from specified directories to the calculation directory, useful for restarting for example.

---
##### **How do I run anything else?**

I implemented various recipes in Quacc for Espresso, you can find them in the [documentation](https://quantum-accelerators.github.io/quacc/user/recipes/recipes_list.html#quantum-espresso). Since I recently extended the ASE Espresso interface to other binaries, it is now possible to use other binaries such as ph.x, pp.x, dos.x, etc...

```python
from quacc.recipes.espresso.core import ase_relax_job
from quacc.recipes.espresso.phonons import phonon_job

relax_results = ase_relax_job(atoms)
phonon_results = phonon_job(relax_results["dir_name"])
```

The above code will run a relaxation calculation using ASE optimizers and then run a phonon calculation using ph.x. Similarly, you can change the parameters of the phonon calculations by passing `input_data` and other parameters to the phonon_job function, everything should be described in the documentation. The Espresso calculator in Quacc takes care of activating restart keywords such as `startingpot` and `startingwfc` during the optimization phase to avoid starting from scratch at each step. Of course, if you want to use the Espresso internal optimizer, you can use the `quacc.recipes.espresso.core.relax_job`{:.python} function.

---

That's it for this post! This is probably the first part of a series of posts about Quacc. Here is what to expect from the next blog posts:

2. Why do we need workflow engines; how to create your own workflows; how to run them on HPC.

3. How to use a monkey-patched version of ASE's NEB class to run calculations concurrently on HPC without the need for explicit parallel code.

4. How to modify an ASE dynamics object to perform additional actions, such as projwfc.x or pp.x jobs at a predefined interval in an optimization or MD run.

In the meantime, if you are interested you can learn more by having a look at the [Quacc documentation](https://quantum-accelerators.github.io/quacc/). Or wait until I write a post about it in the coming days!
