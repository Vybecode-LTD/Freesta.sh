using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Input.Platform;
using Avalonia.Platform.Storage;

namespace Freestash.Desktop.Services;

/// <summary>Clipboard, browser, file manager, and pickers, via the window's TopLevel (Avalonia 12 APIs).</summary>
public sealed class PlatformServices
{
    private TopLevel? _top;

    public void Attach(TopLevel top) => _top = top;

    public TopLevel? TopLevel => _top;

    public async Task CopyTextAsync(string text)
    {
        if (_top?.Clipboard is { } cb) await cb.SetTextAsync(text);
    }

    public async Task<string?> ClipboardTextAsync()
    {
        if (_top?.Clipboard is not { } cb) return null;
        try { return await cb.TryGetTextAsync(); } catch { return null; }
    }

    public async Task OpenUrlAsync(string? url)
    {
        if (_top is null || string.IsNullOrWhiteSpace(url) || !Uri.TryCreate(url, UriKind.Absolute, out var uri)) return;
        await _top.Launcher.LaunchUriAsync(uri);
    }

    public async Task OpenFolderAsync(string? path)
    {
        if (_top is null || string.IsNullOrWhiteSpace(path)) return;
        Directory.CreateDirectory(path);
        await _top.Launcher.LaunchDirectoryInfoAsync(new DirectoryInfo(path));
    }

    public async Task OpenFileAsync(string? path)
    {
        if (_top is null || string.IsNullOrWhiteSpace(path) || !File.Exists(path)) return;
        await _top.Launcher.LaunchFileInfoAsync(new FileInfo(path));
    }

    public async Task<string?> PickFolderAsync(string title, string? startAt = null)
    {
        if (_top is null) return null;
        var options = new FolderPickerOpenOptions { Title = title, AllowMultiple = false };
        if (startAt is not null && Directory.Exists(startAt))
            options.SuggestedStartLocation = await _top.StorageProvider.TryGetFolderFromPathAsync(startAt);
        var picked = await _top.StorageProvider.OpenFolderPickerAsync(options);
        return picked.FirstOrDefault()?.TryGetLocalPath();
    }

    public async Task<bool> SaveTextAsync(string suggestedName, string content, string extension)
    {
        if (_top is null) return false;
        var file = await _top.StorageProvider.SaveFilePickerAsync(new FilePickerSaveOptions
        {
            SuggestedFileName = suggestedName,
            DefaultExtension = extension,
            ShowOverwritePrompt = true,
        });
        if (file is null) return false;
        await using var stream = await file.OpenWriteAsync();
        await using var writer = new StreamWriter(stream);
        await writer.WriteAsync(content);
        return true;
    }

    /// <summary>Drag one or more local files out of the app (Explorer, Finder, DAWs, Figma...).</summary>
    public async Task DragFilesOutAsync(PointerPressedEventArgs trigger, IEnumerable<string> paths)
    {
        if (_top is null) return;
        var transfer = new DataTransfer();
        foreach (var path in paths.Where(File.Exists))
        {
            var file = await _top.StorageProvider.TryGetFileFromPathAsync(path);
            if (file is not null) transfer.Add(DataTransferItem.CreateFile(file));
        }
        await DragDrop.DoDragDropAsync(trigger, transfer, DragDropEffects.Copy);
    }
}
