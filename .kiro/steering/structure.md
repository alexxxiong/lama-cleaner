# Project Structure

## Root Directory
```
lama-cleaner/
├── lama_cleaner/           # Main Python package
├── assets/                 # Demo images and logos
├── docker/                 # Docker configuration files
├── scripts/                # Build and utility scripts
├── requirements.txt        # Python dependencies
├── pyproject.toml         # Modern Python project config
├── setup.py               # Package installation script
└── README.md              # Project documentation
```

## Backend Structure (`lama_cleaner/`)
```
lama_cleaner/
├── __init__.py            # Package initialization
├── __main__.py            # CLI entry point
├── server.py              # Flask web server and API routes
├── model_manager.py       # AI model loading and switching
├── schema.py              # Data models and validation
├── const.py               # Constants and configuration
├── helper.py              # Utility functions
├── parse_args.py          # Command line argument parsing
├── model/                 # AI model implementations
│   ├── base.py           # Base model interface
│   ├── lama.py           # LaMa model
│   ├── sd.py             # Stable Diffusion
│   └── ...               # Other model implementations
├── plugins/               # Post-processing plugins
│   ├── base_plugin.py    # Plugin base class
│   ├── interactive_seg.py # Segment Anything integration
│   ├── realesrgan.py     # Super resolution
│   └── ...               # Other plugins
├── file_manager/          # File system management
└── tests/                 # Test files and test images
```

## Frontend Structure (`lama_cleaner/app/`)
```
app/
├── src/
│   ├── components/        # React components
│   │   ├── Editor/       # Main image editor
│   │   ├── Settings/     # Configuration panels
│   │   ├── FileManager/  # File browser
│   │   ├── shared/       # Reusable UI components
│   │   └── ...
│   ├── hooks/            # Custom React hooks
│   ├── store/            # Recoil state management
│   ├── styles/           # SCSS stylesheets
│   ├── i18n/             # Internationalization
│   │   └── resources/    # Translation files (en, zh-CN)
│   ├── adapters/         # API communication layer
│   └── utils.ts          # Utility functions
├── public/               # Static assets
├── build/                # Production build output
├── config/               # Webpack and build configuration
└── package.json          # Node.js dependencies
```

## Key Conventions

### Python Code
- Follow PEP 8 style guidelines
- Use type hints where applicable
- Modular plugin architecture in `plugins/` directory
- Model implementations inherit from base classes
- Configuration managed through `schema.py` and `const.py`

### Frontend Code
- TypeScript for type safety
- Component-based architecture with React
- SCSS modules for styling
- Recoil atoms for state management
- i18next for internationalization support

### File Organization
- Models: Each AI model has its own implementation file
- Plugins: Self-contained modules with consistent interface
- Components: Organized by feature/functionality
- Styles: Co-located with components or in shared styles directory
- Tests: Mirror the source structure in `tests/` directory

### API Structure
- RESTful endpoints for main operations (`/inpaint`, `/run_plugin`)
- WebSocket communication for real-time progress updates
- File upload handling for images and masks
- JSON configuration for model parameters