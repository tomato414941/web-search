from setuptools import setup, find_packages

setup(
    name="shared",
    version="0.1.0",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.11",
    install_requires=[
        "pydantic>=2.0.0",
        "pydantic-settings>=2.0.0",
        "libsql-experimental>=0.0.50",
        "numpy",
        "sudachipy",
        "sudachidict-core",
        "openai",
        "tenacity",
    ],
)
