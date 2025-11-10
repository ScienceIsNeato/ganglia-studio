from setuptools import setup, find_packages

setup(
    name="ganglia-studio",
    version="0.1.0",
    description="Multimedia generation suite for GANGLIA",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.9",
    install_requires=[
        "ganglia-common>=0.1.0",
        "torch>=2.0.0",
        "transformers>=4.30.0",
        "diffusers>=0.18.0",
        "opencv-python>=4.8.0",
        "moviepy>=1.0.3",
        "pillow>=10.0.0",
        "numpy>=1.24.0",
        "requests>=2.31.0",
        "openai-whisper>=20231117",
        "pydub>=0.25.1",
        "soundfile>=0.12.1",
        "pandas>=2.0.0",
    ],
    entry_points={
        'console_scripts': [
            'ganglia-studio=ganglia_studio.cli:main',
        ],
    },
)
