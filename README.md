# 🌡️ AirControlBase - Home Assistant Integration

[![HACS Badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/bpaludo/aircontrolbase-fork1?include_prereleases&style=flat-square)](https://github.com/bpaludo/aircontrolbase-fork1/releases)
[![GitHub Actions](https://img.shields.io/github/actions/workflow/status/bpaludo/aircontrolbase-fork1/ci.yml?branch=main&style=flat-square)](https://github.com/bpaludo/aircontrolbase-fork1/actions)
[![License](https://img.shields.io/github/license/bpaludo/aircontrolbase-fork1?style=flat-square)](LICENSE)

<p align="center">
  <img src="custom_components/aircontrolbase/logo.png" alt="AirControlBase Logo" width="200"/>
</p>

A custom Home Assistant integration for **AirControlBase** cloud-connected air conditioning devices. Control your AC units directly from Home Assistant with full climate entity support.

---

## ✨ Features

- 🎛️ **Full Climate Control** - Temperature, mode, fan speed, and swing control
- 🔄 **Real-time Updates** - Cloud polling for current device status
- 🏠 **Auto Discovery** - Automatically discovers all devices on your account
- 📱 **Config Flow** - Easy setup through the Home Assistant UI
- 🔐 **Session Recovery** - Automatic re-authentication on session expiry
- 🌡️ **Multiple Modes** - Cool, Heat, Dry, Fan, and Auto modes
- 💨 **Fan Control** - Multiple fan speed settings
- ↕️ **Swing Control** - Vertical swing mode support

## 📋 Requirements

- Home Assistant 2024.1.0 or newer
- AirControlBase account with registered devices
- Internet connectivity for cloud API access

---

## 📦 Installation

### HACS Installation (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots menu (⋮) in the top right
3. Select **"Custom repositories"**
4. Add this repository URL: `https://github.com/bpaludo/aircontrolbase-fork1`
5. Select **"Integration"** as the category
6. Click **"Add"**
7. Search for **"AirControlBase"** in HACS
8. Click **"Download"**
9. Restart Home Assistant

### Existing Home Assistant Installations

If this fork is replacing the original `enudler/homeassistant-aircontrol` installation,
keep the Home Assistant integration domain as `aircontrolbase`.

Do not rename these paths or constants:

```text
custom_components/aircontrolbase
custom_components/aircontrolbase/manifest.json -> "domain": "aircontrolbase"
custom_components/aircontrolbase/const.py -> DOMAIN = "aircontrolbase"
```

To avoid overwriting this fork, make sure HACS is no longer managing the original
repository for this integration before installing this custom repository.

### Manual Installation

1. Download the latest release from the [Releases](https://github.com/bpaludo/aircontrolbase-fork1/releases) page
2. Extract and copy the `custom_components/aircontrolbase` folder to your Home Assistant `config/custom_components/` directory
3. Restart Home Assistant

### Installation from Artifact

For testing pre-release versions:

1. Go to [Actions](https://github.com/bpaludo/aircontrolbase-fork1/actions)
2. Select a successful workflow run
3. Download the `custom_components` artifact
4. Extract and copy to your `config/custom_components/` directory
5. Restart Home Assistant

---

## ⚙️ Configuration

1. Go to **Settings** → **Devices & Services**
2. Click **"+ Add Integration"**
3. Search for **"AirControlBase"**
4. Enter your AirControlBase credentials:
   - **Email**: Your AirControlBase account email
   - **Password**: Your AirControlBase account password
5. Click **Submit**

Your AC devices will be automatically discovered and added as climate entities.

---

## 🔧 Supported Features

| Feature | Support |
|---------|---------|
| Temperature Control | ✅ |
| HVAC Modes (Cool/Heat/Dry/Fan/Auto) | ✅ |
| Fan Speed Control | ✅ |
| Swing Mode | ✅ |
| Power On/Off | ✅ |
| Current Temperature | ✅ |
| Target Temperature | ✅ |

---

## 🛠️ Development

### Prerequisites

- Python 3.11 or 3.12
- Git
- A virtual environment is recommended

### Setup Development Environment

```bash
# Clone the repository
git clone https://github.com/bpaludo/aircontrolbase-fork1.git
cd aircontrolbase-fork1

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install pytest pytest-asyncio pytest-cov aiohttp
```

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run tests with coverage
pytest tests/ --cov=custom_components/aircontrolbase --cov-report=term-missing

# Run a specific test
pytest tests/test_aircontrolbase.py::test_login_success -v
```

### Testing with Real Credentials

For integration testing with actual AirControlBase devices:

```bash
export AIRCONTROLBASE_EMAIL="your@email.com"
export AIRCONTROLBASE_PASSWORD="your_password"
pytest tests/ -v -s
```

### Code Quality

The project uses GitHub Actions for continuous integration:

- **Tests** run on Python 3.11 and 3.12
- **HACS Validation** ensures compatibility with HACS
- **Hassfest Validation** validates Home Assistant integration requirements

---

## 🚀 Release Process

### Creating a New Release

#### Option 1: Using GitHub Actions (Recommended)

1. Go to [Actions](https://github.com/bpaludo/aircontrolbase-fork1/actions)
2. Select **"Create Tag and Release"** workflow
3. Click **"Run workflow"**
4. Enter the version (e.g., `1.0.0`)
5. Choose whether to bump `manifest.json` version
6. Click **"Run workflow"**

The workflow will:
- Validate version format
- Update `manifest.json` if selected
- Run tests and HACS validation
- Create a Git tag
- Create a GitHub Release with artifacts
- Generate changelog from commits

#### Option 2: Manual Tag Release

```bash
# Update version in manifest.json
# Edit custom_components/aircontrolbase/manifest.json

# Commit the change
git add .
git commit -m "chore: Bump version to X.Y.Z"

# Create and push tag
git tag -a "vX.Y.Z" -m "Release vX.Y.Z"
git push origin main --tags
```

### Version Guidelines

We follow [Semantic Versioning](https://semver.org/):

- **MAJOR** (X.0.0): Breaking changes
- **MINOR** (0.X.0): New features, backward compatible
- **PATCH** (0.0.X): Bug fixes, backward compatible

---

## 📊 HACS Compatibility

This integration is designed to be fully compatible with HACS:

### For HACS to Detect Updates

- Releases are published using GitHub Releases
- The `manifest.json` contains the `version` field
- HACS will show available versions in the UI
- Users can select which version to install

### Repository Structure

```
homeassistant-aircontrol/
├── .github/
│   └── workflows/
│       ├── ci.yml              # CI/CD pipeline
│       ├── release.yml         # Auto-release on tags
│       └── create-release.yml  # Manual release workflow
├── custom_components/
│   └── aircontrolbase/
│       ├── __init__.py
│       ├── api.py
│       ├── climate.py
│       ├── config_flow.py
│       ├── const.py
│       ├── logo.png
│       ├── manifest.json
│       └── translations/
├── tests/
│   ├── conftest.py
│   └── test_aircontrolbase.py
├── hacs.json
├── README.md
└── requirements.txt
```

---

## 🐛 Troubleshooting

### Common Issues

#### Authentication Failed
- Verify your AirControlBase credentials are correct
- Check if your account is active on the AirControlBase app
- Ensure your internet connection is stable

#### Devices Not Appearing
- Wait a few minutes after setup for devices to sync
- Check Home Assistant logs for any errors
- Verify devices are visible in the AirControlBase app

#### Session Expired
- The integration automatically handles session recovery
- If issues persist, try removing and re-adding the integration

### Debug Logging

Add to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.aircontrolbase: debug
```

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/bpaludo/aircontrolbase-fork1/issues)
- **Discussions**: [GitHub Discussions](https://github.com/bpaludo/aircontrolbase-fork1/discussions)

---

<p align="center">
  Made with ❤️ for the Home Assistant community
</p>
