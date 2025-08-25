# Product Overview

Lama Cleaner is a free and open-source AI-powered image inpainting tool that removes unwanted objects, people, text, or defects from images. It leverages state-of-the-art AI models to intelligently fill in removed areas.

## Key Features
- Multiple SOTA AI models (LaMa, LDM, ZITS, MAT, FcF, Manga, Stable Diffusion, Paint by Example)
- Cross-platform support (CPU, GPU, Apple M1/M2)
- Web-based interface with React frontend
- Plugin system for post-processing (background removal, super resolution, face restoration)
- File management system for batch processing
- Interactive segmentation with Segment Anything
- Docker deployment support

## Target Users
- Content creators and photographers
- Digital artists and designers
- Anyone needing to clean up images or remove unwanted elements

## Architecture
- Python backend with Flask server and SocketIO for real-time communication
- React TypeScript frontend with modern UI components
- Plugin-based architecture for extensibility
- Model management system supporting multiple AI frameworks (PyTorch, Diffusers, Transformers)