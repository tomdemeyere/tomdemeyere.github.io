---
layout: post
title: Use Parsl to create concurrent computational chemistry workflows
date: 2024-03-20 21:00:00
description: Quacc & Parsl, concurrent workflows for DFT calculations.
tags: Quacc DFT Espresso Parsl
featured: true
related_posts: false
---

A few weeks ago I posted my [first blog post](https://tomdemeyere.github.io/blog/2024/quacc-espresso/) where I explained how to use the new [Quantum Accelerator (Quacc)](https://github.com/Quantum-Accelerators/quacc/) package to run DFT calculations with Quantum Espresso. Quacc allows you to link your favorite DFT code to a workflow manager. In this blog post, I will show you how to use Quacc in combination with the Parsl workflow engine to create concurrent workflows for DFT calculations. This will allow you to run multiple calculations concurrently on your local machine or on a high-performance computing cluster.

### Quacc & Parsl tutorial

If you never run a Quacc calculation before, I recommend you to either read the [Quacc documentation](https://quantum-accelerators.github.io/quacc/) or read my previous blog post. In this blog post, I will assume you have Quacc installed and that you have set up the configuration file correctly.

Before we start, you will need to install [Parsl](https://parsl-project.org):

```bash
pip install parsl
```

Now that you have Parsl installed, you can configure Quacc to use this workflow engine by changing your .quacc.yaml:

```bash
quacc set WORKFLOW_ENGINE parsl
```

For the purpose of this tutorial we will use the open-source plane-wave [Quantum Espresso](https://www.quantum-espresso.org) code, I will assume a similar setup than in my [previous blog-post](https://tomdemeyere.github.io/blog/2024/quacc-espresso/): 

- `ESPRESSO_PSEUDO` is set to a folder that contains the full [SSSP 1.3.0 efficiency](https://www.materialscloud.org/discover/sssp/table/efficiency) pseudopotential library.
- `ESPRESSO_BIN_DIR` is set to the path of the Quantum Espresso binaries.

The aim of the tutorial is to compute the phonon dispersion of multiple bulk crystals using the espresso `ph.x` code. The `grid_phonon_flow` [available in Quacc](https://quantum-accelerators.github.io/quacc/reference/quacc/recipes/espresso/phonons.html#quacc.recipes.espresso.phonons.grid_phonon_flow) will make this problem embarrassingly parallel by performing each representation of each q-points separately. Using Parsl these calculations are then done concurrently automatically depending on the resources available.

The base code to run this calculation is fairly simple, it first runs a variable-cell relaxation, and then uses the results to run the phonon calculation. From there we can extract the force constant using `q2r.x` and then call `matdyn.x` to compute the phonon dispersion on an arbitrary q-point grid. The main function is described below, for now, let's skip the technical details and focus on the functions being called:

- `grid_phonon_flow` is a pre-made `@flow` in Quacc, that contains multiple `@job`, details can be found in the documentation.
- `q2r_job` is a pre-made `@job` that runs the `q2r.x`.
- `matdyn_job` is a pre-made `@job` that runs the `matdyn.x`.

``` python
@subflow
def grid_phonon_dos_subflow(atoms_list):

    results = []

    for atoms in atoms_list:
        grid_phonon_results = grid_phonon_flow(
            atoms,
            job_params=grid_phonon_params,
        )
        q2r_results = q2r_job(grid_phonon_results["dir_name"], **q2r_params)
        matdyn_results = matdyn_job(q2r_results["dir_name"], **matdyn_params)
        results.append(matdyn_results)

    return results
```

The aim is then simple, we take a list of ASE `Atoms` objects, and we run this custom workflow for each of them. Each results are then stored in a list and returned.

---

##### **Setting up Parsl**

You will need to configure Parsl before using it. In this tutorial, Parsl is run locally and will submit each job to an HPC scheduler (Slurm in this tutorial). All these options need to be specified via the Parsl configuration. Of course, as done similarly in my previous post, you can perfectly run this code without setting up any workflow engine. 

``` python
from parsl.config import Config
from parsl.executors import HighThroughputExecutor
from parsl.launchers import SimpleLauncher
from parsl.providers import SlurmProvider

CONFIG = Config(
    executors=[
        HighThroughputExecutor(
            label="short-large",
            max_workers=32,  # max number of @job to run concurently.
            cores_per_worker=1.0e-6,  # number of cores per worker, < 1 to oversubscribe.
            provider=SlurmProvider(
                account="e89-soto",  # your account code.
                qos="short",  # which quality of service.
                worker_init=worker_init,  # bash lines that will run before each @job
                walltime="00:20:00",
                nodes_per_block=32,  # nodes for each slurm job (block)
                cores_per_node=1,  # How many threads to use per parsl worker.
                partition="standard",
                init_blocks=0,  # To be kept to 0, especially if you are using different executors.
                max_blocks=1,  # Max number of slurm_jobs.
                launcher=SimpleLauncher(),  # Control where Parsl will live,
            ),
        ),
    ]
)

parsl.load(CONFIG)
```

The terminology is a bit different from what you might be used to, here is a quick summary:

- `blocks` is the number of actual Slurm jobs. You have total control over that by using the keywords `init_blocks`, `min_blocks` and `max_blocks`. By default, the pilot job model is used, which means that `max_blocks = 1`, you can increase this number to fit your needs.

- `workers` is also a concept introduced by Parsl, this is a computing unit that will take care of running a `@job`. In practice, this number will dictate how many of your `@job`'s can run concurrently.

- `launcher` dictates how the Parsl command is wrapped before being launched, the `SimpleLauncher` used here means that it does not use any wrapping; the Parsl process will only run on the mother node. The `SingleNodeLauncher` will run the parsl process on each node, and might be used as well.

- `cores_per_worker` is the number of cores that will be used by each worker. In the case of computational chemistry, you will often see that it is set to something very low, this means that multiple workers can live on the same threads. There is no need to tweak `cores_per_node`.

These parallelization options are not to be seen as the ones that will affect your individual DFT calculations but more as a **total** parallelization that will dictate how many resources this `executor` can use. Your DFT calculations are then dispatched inside this executor, their parallelization will be specified later.

`worker_init` should have everything you need to run espresso, the machine I use does not have access to the home system from the compute nodes, so I need to to load a 'scratch' bashrc that contains the conda init. This is done by adding the following lines:

``` python
worker_init = """
source /path/inside/scratch/.bashrc # Load your bashrc that contains the conda init.
conda activate quacc # Activate the conda environment.

export QUACC_CONFIG_FILE=/path/inside/scratch/.quacc.yaml # Quacc config in scratch space.

module load PrgEnv-gnu
module load cray-fftw cray-hdf5-parallel

export LD_LIBRARY_PATH=$CRAY_LD_LIBRARY_PATH:$LD_LIBRARY_PATH
"""
```

---

##### **Specifying parameters and parallelization**

Before running the workflow you need to setup the parameters that will be sent to each flow and job, namely the `grid_phonon_params`, `matdyn_params`, and `q2r_params`. For the parallelization, currently, the Quacc Espresso interface uses the new `parallel_info` mechanism introduced in ASE. Here we will use the `srun` command with its options. This is done by setting the `parallel_info` variable in the `grid_phonon_params` and `matdyn_params` dictionaries.

``` python
parallel_info = {
    "binary": "srun",
    "-vv": True,
    "--hint=nomultithread": True,
    "--distribution=block:block": True,
    "-N": 1,
    "-n": 128,
    "-c": 1,
}

pw_input_data = {
    "control": {"forc_conv_thr": 0.0001},
    "system": {
        "occupations": "smearing",
        "degauss": 0.01,
        "smearing": "cold",
    },
    "electrons": {"conv_thr": 1e-12, "mixing_mode": "TF", "mixing_beta": 0.7},
    "ions": {},
    "cell": {"press_conv_thr": 0.1},
}

ph_input_data = {
    "inputph": {
        "tr2_ph": 1.0e-12,
        "alpha_mix(1)": 0.1,
        "nmix_ph": 8,
        "ldisp": True,
        "nq1": 5,
        "nq2": 5,
        "nq3": 5,
    },
}

matdyn_input_data = {
    "input": {
        "asr": "crystal",
        "dos": True,
        "nk1": 32,
        "nk2": 32,
        "nk3": 32,
        "deltaE": 0.5,
    },
}

grid_phonon_params = {
    "relax_job": {
        "input_data": pw_input_data,
        "kspacing": 0.1,
        "relax_cell": True,
        "parallel_info": parallel_info,
    },
    "ph_job": {
        "input_data": ph_input_data,
        "parallel_info": parallel_info,
    },
}

matdyn_params = {
    "input_data": matdyn_input_data,
    "parallel_info": parallel_info,
}

q2r_params = {
    "parallel_info": parallel_info,
}
```

All these lines and config are to be placed before the `@subflow` "grid_phonon_dos_subflow". You can access the complete script on my GitHub page. At this point, you can create an atoms list of bulk crystals and call the function.

``` python
from ase.build import bulk

atoms_list = [
    bulk("Al", cubic=True),
    bulk("Cu", cubic=True),
    bulk("Ag", cubic=True),
    bulk("Au", cubic=True),
    bulk("Ni", cubic=True),
    bulk("Pd", cubic=True),
    bulk("Pt", cubic=True),
    bulk("Li", cubic=True),
]

future = grid_phonon_dos_flow(atoms_list)
```

At this stage, running the Python script doesn't produce any output. This is because Parsl is now handling the function call, and it is only generating the [Directed Acyclic Graph (DAG)]((https://en.wikipedia.org/wiki/Directed\_acyclic\_graph)), which is an internal representation of the workflow. The returned object is a future object. To actually execute the workflow, the future object needs to be resolved by calling the `Future.result()` method.

``` python
results = future.result()
```

If you have important disparities between the size of your jobs, Parsl allows you to define multiple executors. To do this, you just need to add a new executor to the `CONFIG` object. You simply need to add one more executor to the list. I will not show it here, but the code is available on my [GitHub](https://github.com/tomdemeyere/tomdemeyere.github.io/blob/master/code_snippets/blog-post-2.py). Using Quacc each job can be linked to a single executor to make sure to run your jobs using the resources you want.

``` python
q2r_job_custom = redecorate(q2r_job, job(executors=["q2r"]))
matdyn_job_custom = redecorate(matdyn_job, job(executors=["matdyn"]))
```

---

##### **What will happen exactly?**

Parsl will construct the workflow internally and be able to manage the intrinsic dependencies between the jobs. Two jobs that do not depend on each other can possibly run at the same time. To make things clearer I made the diagram below that summarizes what is happening.


{% include figure.html path="assets/img/grid_phonon_flow.png" class="img-fluid rounded" %}
<div class="caption">
    Schematic of the workflow, all `Atoms` objects will run concurrently, similarly all identical colors within each subtask can run concurrently as well. This makes the problem embarrassingly parallel.
</div>

Depending on the number of workers you have set, you will see as many concurrent calculations, other tasks will be queued and run as soon as a worker is available.

---

##### **Where is the output?**

When using Parsl things are a little bit different, the output will mainly be located in the `runinfo` dir located in the current working directory. This directory will contain a lot of information about the workflow, including the Parsl logs. You can see the log for each worker in the `runinfo/<executor_label>` directory. 

---

##### **I want to use a different interface than Slurm/srun, how?**

Parsl is very flexible and can be used with a [lot of different interfaces](https://parsl.readthedocs.io/en/stable/userguide/configuring.html). The `SlurmProvider` is only one of them. However, running MPI apps is a tricky business, as of now (25th March 2024), Quacc does not support commands that do not automatically allocate resources for a job such as mpirun/mpiexec or other exotic executables. The underlying technical reason is that Quacc does not communicate to Parsl the size of each job. This is currently [being implemented](https://github.com/Quantum-Accelerators/quacc/issues/1886).

---

##### **What if one job fails?**

Parsl is able to handle this, if a job fails, every other jobs that do not have the failed job as a dependency will run. This is a very powerful feature that allows to run high-throughput workflows without having to worry too much about the stability of the system. Be aware that the `future.result()` will still raise an exception if a job fails.