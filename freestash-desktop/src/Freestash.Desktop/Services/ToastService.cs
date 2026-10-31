using Avalonia.Threading;
using CommunityToolkit.Mvvm.ComponentModel;

namespace Freestash.Desktop.Services;

/// <summary>One transient message at a time, bottom-center. Safe to call from any thread.</summary>
public sealed partial class ToastService : ObservableObject
{
    private CancellationTokenSource? _cts;

    [ObservableProperty] public partial string? Message { get; set; }

    public bool IsVisible => Message is not null;

    partial void OnMessageChanged(string? value) => OnPropertyChanged(nameof(IsVisible));

    public void Show(string message, int ms = 2800) => Dispatcher.UIThread.Post(async () =>
    {
        _cts?.Cancel();
        var cts = _cts = new CancellationTokenSource();
        Message = message;
        try { await Task.Delay(ms, cts.Token); Message = null; }
        catch (TaskCanceledException) { }
    });
}
