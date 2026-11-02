namespace Freestash.Client.Account;

/// <summary>Which of the mutually exclusive statuses a member's key row shows.</summary>
public enum KeyTone { Set, Site, Optional, Missing, Removing }

/// <summary>
/// The member key row's status: one rule, the same words as the web's <c>lib/admin.ts::memberKeyStatus</c> (the web
/// upper-cases them in CSS). Exactly one tone per row, so a pending removal can never leave a row without a label.
/// </summary>
public static class KeyStatus
{
    /// <param name="saved">The member has a key of their own (in the account, or on this computer).</param>
    /// <param name="hint">Its last four characters, when the account holds it.</param>
    /// <param name="removing">The member pressed remove and hasn't saved yet.</param>
    /// <param name="site">Freesta.sh has its own key for this source (decision 0003).</param>
    /// <param name="optional">The source works without any key.</param>
    public static (KeyTone Tone, string Text) For(bool saved, string? hint, bool removing, bool site, bool optional) =>
        removing ? (KeyTone.Removing, "WILL BE REMOVED")
        : saved ? (KeyTone.Set, hint is { } h ? $"YOURS · …{h}" : "SET")
        : site ? (KeyTone.Site, "FREESTA.SH'S KEY")
        : optional ? (KeyTone.Optional, "OPTIONAL")
        : (KeyTone.Missing, "NOT SET");
}
