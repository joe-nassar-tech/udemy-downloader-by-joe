# How to Create a Release

## 🚀 Creating Your First Release

Now that the release workflow is set up, you can create releases easily:

### Method 1: Using Git Tags (Recommended)

1. **Commit your changes:**
   ```bash
   git add .
   git commit -m "Prepare for release v1.0.0"
   ```

2. **Create and push a tag:**
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```

3. **The workflow will automatically:**
   - Create a release on GitHub
   - Package all necessary files
   - Generate release notes
   - Upload the packaged ZIP file

### Method 2: Using GitHub Web Interface

1. Go to your repository on GitHub
2. Click on "Releases" in the sidebar (or go to `/releases`)
3. Click "Create a new release"
4. Choose a tag version (e.g., `v1.0.0`)
5. Add release title and description
6. Publish the release

## 📋 What Gets Included in Releases

The automated release includes:
- All Python source files
- Requirements.txt
- Documentation files (README, LICENSE, etc.)
- Example configuration files
- Required executables (if present)
- Pre-created directory structure

## 🏷️ Version Naming Convention

Use semantic versioning:
- `v1.0.0` - Major release
- `v1.1.0` - Minor update/new features  
- `v1.0.1` - Bug fixes/patches

## 🔄 Testing the Release

After creating a release:
1. Download the ZIP from the releases page
2. Extract and test the installation process
3. Verify all files are included and working

---

**Note:** Delete this file after creating your first release, as it's just a guide. 