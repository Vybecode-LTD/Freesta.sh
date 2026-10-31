using Avalonia.Controls;
using Avalonia.Input;
using Freestash.Desktop.ViewModels;

namespace Freestash.Desktop.Views;

public partial class DownloadsView : UserControl
{
    public DownloadsView()
    {
        InitializeComponent();
        // Drop text or links onto the paste box (Avalonia 12 DataTransfer API).
        PasteBox.AddHandler(DragDrop.DragOverEvent, OnDragOver);
        PasteBox.AddHandler(DragDrop.DropEvent, OnDrop);
    }

    private static void OnDragOver(object? sender, DragEventArgs e)
    {
        e.DragEffects = e.DataTransfer.Contains(DataFormat.Text) ? DragDropEffects.Copy : DragDropEffects.None;
        e.Handled = true;
    }

    private void OnDrop(object? sender, DragEventArgs e)
    {
        if (DataContext is not DownloadsViewModel vm) return;
        var text = e.DataTransfer.TryGetText();
        if (string.IsNullOrWhiteSpace(text)) return;
        vm.PasteText = string.IsNullOrWhiteSpace(vm.PasteText) ? text : vm.PasteText.TrimEnd() + Environment.NewLine + text;
        e.Handled = true;
    }

    /// <summary>Drag a finished download (and its .license.json sidecar) out to the OS or another app.</summary>
    private async void OnDragHandlePressed(object? sender, PointerPressedEventArgs e)
    {
        if (sender is not Control { DataContext: DownloadItemViewModel { IsDone: true } item }) return;
        if (!e.GetCurrentPoint(this).Properties.IsLeftButtonPressed) return;
        var paths = new List<string>();
        if (item.Job.LocalPath is { } file) paths.Add(file);
        if (item.Job.SidecarPath is { } sidecar) paths.Add(sidecar);
        await App.Services.Platform.DragFilesOutAsync(e, paths);
    }
}
