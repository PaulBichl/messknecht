Getting Started
===============

Installation
------------

From PyPI (when published)::

    pip install your-package

From source::

    git clone https://github.com/yourusername/your-repo
    cd your-repo
    pip install -e ".[dev]"

Development Setup
-----------------

Create a development environment::

    hatch env create

Install pre-commit hooks::

    hatch run fix install

Verify installation::

    hatch run type    # Type checking
    hatch run style   # Lint check
    hatch run test    # Run tests

Basic Usage
-----------

Run your package::

    python -m messknecht

Or import and use it::

    from messknecht.main import main
    main()

Add your own modules in ``messknecht/`` following the patterns in the codebase.

Next Steps
----------

- Customize `main.py` with your code
- Add modules to `messknecht/`
- Write tests in `tests/`
- Check `CONTRIBUTING.md` for development workflow

Troubleshooting
---------------

**Module not found error**
    Make sure you've installed the package: ``pip install -e .``

**Type checking fails**
    Run ``hatch run type --install-types`` to install type stubs

**Pre-commit hooks fail**
    Run ``hatch run fix --all-files`` to auto-fix issues
