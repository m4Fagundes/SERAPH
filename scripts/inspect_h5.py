import h5py
import os

# Search for the file first
print("Buscando patient_001*.h5 no OneDrive...")
for root, dirs, files in os.walk(r"C:\Users\mathe\OneDrive"):
    # skip venv folders
    dirs[:] = [d for d in dirs if d != "venv"]
    for f in files:
        if "patient_001" in f and f.endswith(".h5"):
            full = os.path.join(root, f)
            print(f"  ENCONTRADO: {full}")

print()
path = r"C:\Users\mathe\OneDrive\Documentos\MyLife\Scientific Research\SERAPH\patient_001 (1).h5"
print(f"Procurando: {path}")
print(f"Existe: {os.path.exists(path)}")
print()

with h5py.File(path, "r") as f:
    for key in f.keys():
        ds = f[key]
        if ds.shape[0] > 0 and len(ds.shape) <= 2:
            sample = repr(ds[0])
        else:
            sample = "..."
        print(f"{key}:")
        print(f"  shape       = {ds.shape}")
        print(f"  dtype       = {ds.dtype}")
        print(f"  chunks      = {ds.chunks}")
        print(f"  compression = {ds.compression}")
        print(f"  sample[0]   = {sample}")
        print()
