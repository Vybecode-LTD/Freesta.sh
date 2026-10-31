using System.Diagnostics;
using Freestash.Client.Settings;

namespace Freestash.Client.Engine;

public enum EngineState { Unknown, Starting, Online, Offline, Error }

/// <summary>
/// Keeps a Freestash server reachable. Local mode: if nothing answers on the port, spawn
/// `python -m freestash serve --port N` with the user's API keys as environment variables, and stop it on exit.
/// Remote mode: just health-check the team server.
/// </summary>
public sealed class EngineHost : IAsyncDisposable
{
    private readonly Func<AppSettings> _settings;
    private readonly SecretStore _secrets;
    private readonly Func<IFreestashApi> _api;
    private readonly LinkedList<string> _log = new();
    private Process? _process;

    public EngineHost(Func<AppSettings> settings, SecretStore secrets, Func<IFreestashApi> api)
    {
        _settings = settings;
        _secrets = secrets;
        _api = api;
    }

    public EngineState State { get; private set; } = EngineState.Unknown;
    public string StatusText { get; private set; } = "Not connected";
    public string? Version { get; private set; }
    public bool OwnsProcess => _process is { HasExited: false };
    public IReadOnlyCollection<string> Log { get { lock (_log) return _log.ToList(); } }

    public event Action? StateChanged;

    private void SetState(EngineState state, string text)
    {
        State = state;
        StatusText = text;
        StateChanged?.Invoke();
    }

    public async Task<bool> PingAsync(CancellationToken ct = default)
    {
        var s = _settings();
        try
        {
            var health = await _api().HealthAsync(ct);
            Version = health.Version;
            var where = s.Mode == ConnectionMode.Remote ? s.ApiBaseUri.Host : $"local :{s.LocalPort}";
            SetState(EngineState.Online, $"Engine {health.Version} · {where}{(OwnsProcess ? "" : s.Mode == ConnectionMode.Local ? " (external)" : "")}");
            return true;
        }
        catch (Exception) when (!ct.IsCancellationRequested)
        {
            return false;
        }
    }

    public async Task EnsureRunningAsync(CancellationToken ct = default)
    {
        if (await PingAsync(ct)) return;
        var s = _settings();
        if (s.Mode == ConnectionMode.Remote)
        {
            SetState(EngineState.Offline, $"Can't reach {s.ApiBaseUri.Host}");
            return;
        }
        if (!s.AutoStartEngine)
        {
            SetState(EngineState.Offline, "Engine offline · start it or enable auto-start in Settings");
            return;
        }
        await StartLocalAsync(ct);
    }

    public async Task RestartAsync(CancellationToken ct = default)
    {
        await StopAsync();
        await EnsureRunningAsync(ct);
    }

    /// <summary>Environment for the Python engine: API keys + identity. Exposed for tests.</summary>
    public IDictionary<string, string> BuildEnvironment()
    {
        var s = _settings();
        var env = new Dictionary<string, string>
        {
            ["FREESTASH_AUTH_MODE"] = "none",
            ["PYTHONUNBUFFERED"] = "1",
            ["FREESTASH_CORS_ORIGINS"] = "[]",
        };
        if (!string.IsNullOrWhiteSpace(s.ContactEmail)) env["FREESTASH_CONTACT_EMAIL"] = s.ContactEmail.Trim();
        foreach (var key in ProviderKeys.All)
            if (_secrets.Get(key.EnvVar) is { } value) env[key.EnvVar] = value;
        return env;
    }

    private async Task StartLocalAsync(CancellationToken ct)
    {
        var s = _settings();
        SetState(EngineState.Starting, $"Starting engine on :{s.LocalPort}…");
        var psi = new ProcessStartInfo(s.PythonCommand)
        {
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
        };
        foreach (var a in new[] { "-m", "freestash", "serve", "--host", "127.0.0.1", "--port", s.LocalPort.ToString() }) psi.ArgumentList.Add(a);
        foreach (var (k, v) in BuildEnvironment()) psi.Environment[k] = v;

        try
        {
            _process = Process.Start(psi) ?? throw new InvalidOperationException("process did not start");
        }
        catch (Exception ex)
        {
            SetState(EngineState.Error, $"Couldn't run '{s.PythonCommand} -m freestash': {ex.Message}. Install Freestash (python -m pip install -e .) or set the Python command in Settings.");
            return;
        }
        _process.OutputDataReceived += (_, e) => AppendLog(e.Data);
        _process.ErrorDataReceived += (_, e) => AppendLog(e.Data);
        _process.BeginOutputReadLine();
        _process.BeginErrorReadLine();

        for (var i = 0; i < 60 && !ct.IsCancellationRequested; i++)
        {
            await Task.Delay(250, ct);
            if (_process.HasExited)
            {
                var tail = string.Join(" ", Log.TakeLast(3));
                SetState(EngineState.Error, $"Engine exited (code {_process.ExitCode}). {tail}");
                return;
            }
            if (await PingAsync(ct)) return;
        }
        SetState(EngineState.Error, "Engine didn't answer within 15s. Check Settings → Engine log.");
    }

    private void AppendLog(string? line)
    {
        if (string.IsNullOrEmpty(line)) return;
        lock (_log)
        {
            _log.AddLast(line);
            while (_log.Count > 400) _log.RemoveFirst();
        }
    }

    public async Task StopAsync()
    {
        if (_process is { HasExited: false } p)
        {
            try
            {
                p.Kill(entireProcessTree: true);
                await p.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(5));
            }
            catch (Exception) { /* already gone */ }
        }
        _process = null;
        SetState(EngineState.Offline, "Engine stopped");
    }

    public async ValueTask DisposeAsync() => await StopAsync();
}
