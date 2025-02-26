# Optional dependency modules
Some modules have optional dependency such as
* nvflare.fuel_opt
* nvflare.app_opt

The nvflare/fuel_opt is the module with components or files which **optional** dependencies.
That means there are dependencies are not required to be installed when user type
 ```
     pip install nvflare
 ```
* you will need to install the required python package separately or use

```
  pip install nvflare[core_opt]
```
to install optional dependency for core modules: the core module includes nvflare.fuel etc.  

* If you are interested in CONFIG package only 

```
  pip install nvflare[CONFIG]
```
CONFIG is part of the core, so core_opt will include optional packages for config and other cores.  

* to install optional dependency for application level module, use

```
  pip install nvflare[apt_opt]
```
to install all optional dependency, use

```
  pip install nvflare[all]
```

## Security Components

1. **IO Interceptor** (`tool/io_interceptor`)
  - Protects file I/O operations
  - Secures memory operations
  - System call interception
  - Focuses on storage & memory security

2. **System Hardening** (`tool/system_hardening`)
  - Handles all network security
  - Network security and isolation
  - Port management
  - Traffic control
  - System lockdown

3. **TEE Integration**
  - Memory encryption
  - Hardware isolation
  - Attestation support
