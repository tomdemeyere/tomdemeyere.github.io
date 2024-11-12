from ase.build import bulk
from parsl.config import Config
from parsl.executors import HighThroughputExecutor
from parsl.launchers import SimpleLauncher
from parsl.providers import SlurmProvider
from quacc import subflow
from quacc.recipes.espresso.phonons import (grid_phonon_flow, matdyn_job,
                                            q2r_job)

worker_init = """
source /path/inside/scratch/.bashrc # Load your bashrc that contains the conda init.
conda activate quacc # Activate the conda environment.

export QUACC_CONFIG_FILE=/path/inside/scratch/.quacc.yaml # Quacc config in scratch space.

module load PrgEnv-gnu
module load cray-fftw cray-hdf5-parallel

export LD_LIBRARY_PATH=$CRAY_LD_LIBRARY_PATH:$LD_LIBRARY_PATH
"""

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

future = grid_phonon_dos_subflow(atoms_list)

results = future.result()
