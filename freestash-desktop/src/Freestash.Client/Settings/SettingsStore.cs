using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Freestash.Client.Settings;

public static class AppPaths
{
    /// <summary>%APPDATA%\Freestash on Windows, ~/Library/Application Support/Freestash on macOS, ~/.config/Freestash on Linux.</summary>
    public static string ConfigDirectory(string? overrideRoot = null)
    {
        var root = overrideRoot ?? Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
        var dir = Path.Combine(root, "Freestash");
        Directory.CreateDirectory(dir);
        return dir;
    }

    public static string CacheDirectory()
    {
        var dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Freestash", "cache");
        Directory.CreateDirectory(dir);
        return dir;
    }
}

public sealed class SettingsStore(string directory)
{
    private static readonly JsonSerializerOptions Json = new()
    {
        WriteIndented = true,
        Converters = { new JsonStringEnumConverter() },
    };

    public string FilePath => Path.Combine(directory, "settings.json");

    public AppSettings Load()
    {
        try
        {
            return File.Exists(FilePath) ? JsonSerializer.Deserialize<AppSettings>(File.ReadAllText(FilePath), Json) ?? new() : new();
        }
        catch (JsonException)
        {
            File.Copy(FilePath, FilePath + ".corrupt", overwrite: true);
            return new AppSettings();
        }
    }

    public void Save(AppSettings settings)
    {
        var tmp = FilePath + ".tmp";
        File.WriteAllText(tmp, JsonSerializer.Serialize(settings, Json));
        File.Move(tmp, FilePath, overwrite: true);
    }
}

/// <summary>
/// Encrypted key/value store for API keys and tokens.
/// Windows: DPAPI (CurrentUser scope), so only this Windows account can decrypt.
/// macOS/Linux: AES-256-GCM with a random per-user key file (chmod 600). Keychain/libsecret is a
/// planned upgrade (IMPLEMENTATION.md D4); the file format carries a version byte for that migration.
/// </summary>
public sealed class SecretStore
{
    private const byte FormatDpapi = 1;
    private const byte FormatAesGcm = 2;
    private static readonly byte[] Entropy = "freestash-desktop/secrets/v1"u8.ToArray();

    private readonly string _path;
    private readonly string _keyPath;
    private readonly bool _useDpapi;
    private Dictionary<string, string> _values = new(StringComparer.Ordinal);

    public SecretStore(string directory, bool? forceDpapi = null)
    {
        _path = Path.Combine(directory, "secrets.bin");
        _keyPath = Path.Combine(directory, ".secret-key");
        _useDpapi = forceDpapi ?? OperatingSystem.IsWindows();
        Load();
    }

    public string? Get(string name) => _values.TryGetValue(name, out var v) && v.Length > 0 ? v : null;

    public void Set(string name, string? value)
    {
        if (string.IsNullOrWhiteSpace(value)) _values.Remove(name);
        else _values[name] = value.Trim();
    }

    public IReadOnlyDictionary<string, string> All => _values;

    public void Save()
    {
        var plain = JsonSerializer.SerializeToUtf8Bytes(_values);
        byte[] blob = _useDpapi ? [FormatDpapi, .. ProtectDpapi(plain)] : [FormatAesGcm, .. ProtectAes(plain)];
        CryptographicOperations.ZeroMemory(plain);
        var tmp = _path + ".tmp";
        File.WriteAllBytes(tmp, blob);
        File.Move(tmp, _path, overwrite: true);
    }

    private void Load()
    {
        if (!File.Exists(_path)) return;
        var blob = File.ReadAllBytes(_path);
        if (blob.Length < 2) return;
        try
        {
            var plain = blob[0] switch
            {
                FormatDpapi => UnprotectDpapi(blob[1..]),
                FormatAesGcm => UnprotectAes(blob[1..]),
                _ => throw new CryptographicException("unknown secret format"),
            };
            _values = JsonSerializer.Deserialize<Dictionary<string, string>>(plain) ?? new(StringComparer.Ordinal);
            CryptographicOperations.ZeroMemory(plain);
        }
        catch (CryptographicException)
        {
            // Copied from another machine/user or corrupted: keep a backup, start empty.
            File.Copy(_path, _path + ".unreadable", overwrite: true);
            _values = new(StringComparer.Ordinal);
        }
    }

    private static byte[] ProtectDpapi(byte[] plain)
    {
        if (!OperatingSystem.IsWindows()) throw new PlatformNotSupportedException("DPAPI is Windows-only");
        return ProtectedData.Protect(plain, Entropy, DataProtectionScope.CurrentUser);
    }

    private static byte[] UnprotectDpapi(byte[] blob)
    {
        if (!OperatingSystem.IsWindows()) throw new CryptographicException("DPAPI blob on a non-Windows OS");
        return ProtectedData.Unprotect(blob, Entropy, DataProtectionScope.CurrentUser);
    }

    private byte[] Key()
    {
        if (File.Exists(_keyPath)) return Convert.FromBase64String(File.ReadAllText(_keyPath).Trim());
        var key = RandomNumberGenerator.GetBytes(32);
        File.WriteAllText(_keyPath, Convert.ToBase64String(key));
        if (!OperatingSystem.IsWindows())
            File.SetUnixFileMode(_keyPath, UnixFileMode.UserRead | UnixFileMode.UserWrite);
        return key;
    }

    private byte[] ProtectAes(byte[] plain)
    {
        var nonce = RandomNumberGenerator.GetBytes(12);
        var tag = new byte[16];
        var cipher = new byte[plain.Length];
        using var aes = new AesGcm(Key(), 16);
        aes.Encrypt(nonce, plain, cipher, tag, Entropy);
        return [.. nonce, .. tag, .. cipher];
    }

    private byte[] UnprotectAes(byte[] blob)
    {
        var nonce = blob[..12];
        var tag = blob[12..28];
        var cipher = blob[28..];
        var plain = new byte[cipher.Length];
        using var aes = new AesGcm(Key(), 16);
        aes.Decrypt(nonce, cipher, tag, plain, Entropy);
        return plain;
    }
}
