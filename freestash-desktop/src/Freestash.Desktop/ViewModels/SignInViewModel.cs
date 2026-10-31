using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Freestash.Client;
using Freestash.Client.Settings;
using Freestash.Desktop.Services;

namespace Freestash.Desktop.ViewModels;

/// <summary>Sign in / create account / reset link. The same account as freesta.sh on the web (same API, same token).</summary>
public sealed partial class SignInViewModel(AppServices services) : ViewModelBase
{
    public enum Mode { SignIn, SignUp, Forgot }

    [ObservableProperty] public partial Mode Current { get; set; } = Mode.SignIn;
    [ObservableProperty] public partial string Email { get; set; } = "";
    [ObservableProperty] public partial string Password { get; set; } = "";
    [ObservableProperty] public partial string DisplayName { get; set; } = "";
    [ObservableProperty] public partial string? Error { get; set; }
    [ObservableProperty] public partial string? Note { get; set; }
    [ObservableProperty] public partial bool IsBusy { get; set; }

    public bool IsSignIn => Current == Mode.SignIn;
    public bool IsSignUp => Current == Mode.SignUp;
    public bool IsForgot => Current == Mode.Forgot;
    public bool ShowPassword => Current != Mode.Forgot;
    public string Title => Current switch { Mode.SignUp => "Create your account", Mode.Forgot => "Reset your password", _ => "Sign in" };
    public string Cta => Current switch { Mode.SignUp => "Create account", Mode.Forgot => "Email me a reset link", _ => "Sign in" };
    public bool HasError => !string.IsNullOrEmpty(Error);
    public bool HasNote => !string.IsNullOrEmpty(Note);
    public string ServerHost => services.Settings.ApiBaseUri.Host;

    partial void OnCurrentChanged(Mode value)
    {
        Error = null;
        foreach (var p in new[] { nameof(IsSignIn), nameof(IsSignUp), nameof(IsForgot), nameof(ShowPassword), nameof(Title), nameof(Cta) })
            OnPropertyChanged(p);
    }

    partial void OnErrorChanged(string? value) => OnPropertyChanged(nameof(HasError));
    partial void OnNoteChanged(string? value) => OnPropertyChanged(nameof(HasNote));

    [RelayCommand] private void ShowSignIn() { Current = Mode.SignIn; Note = null; }
    [RelayCommand] private void ShowSignUp() => Current = Mode.SignUp;
    [RelayCommand] private void ShowForgot() => Current = Mode.Forgot;

    [RelayCommand]
    private async Task SubmitAsync()
    {
        if (IsBusy) return;
        IsBusy = true;
        Error = null;
        Note = null;
        try
        {
            var account = services.Account.Current;
            switch (Current)
            {
                case Mode.SignIn:
                    await services.SignedInAsync(await account.LoginAsync(Email.Trim(), Password));
                    Password = "";
                    break;
                case Mode.SignUp:
                    await services.SignedInAsync(await account.RegisterAsync(Email.Trim(), Password, string.IsNullOrWhiteSpace(DisplayName) ? null : DisplayName.Trim()));
                    Password = "";
                    break;
                case Mode.Forgot:
                    await account.ForgotAsync(Email.Trim());
                    Current = Mode.SignIn;
                    Note = "If that email has an account, a reset link is on its way. Open it in your browser, then sign in here.";
                    break;
            }
        }
        catch (FreestashApiException ex) { Error = ex.Message; }
        catch (HttpRequestException) { Error = $"Can't reach {ServerHost}. Check your connection, or use a local engine in Settings."; }
        catch (TaskCanceledException) { Error = $"{ServerHost} took too long to answer. Try again."; }
        finally { IsBusy = false; }
    }

    /// <summary>For people running the Python engine themselves: no account needed.</summary>
    [RelayCommand]
    private async Task UseLocalEngineAsync()
    {
        var s = services.SettingsStore.Load();
        s.Mode = ConnectionMode.Local;
        services.SaveSettings(s);
        await services.Engine.RestartAsync();
        services.Session.Set(null); // raises Changed, so the shell re-evaluates NeedsSignIn
    }
}
