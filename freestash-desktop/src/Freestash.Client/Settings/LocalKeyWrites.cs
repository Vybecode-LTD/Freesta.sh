namespace Freestash.Client.Settings;

/// <summary>One provider-key row as Settings shows it when the user saves.</summary>
public readonly record struct KeyEdit(string Name, string Value, bool Dirty, bool Removing);

/// <summary>
/// What a Settings save writes into this machine's <see cref="SecretStore"/>. Rows shown from the account hold only
/// masked states (empty values), so they never touch the local keys, not even while switching to the local engine;
/// local rows write only what the user changed.
/// </summary>
public static class LocalKeyWrites
{
    public static void Apply(SecretStore secrets, bool rowsFromAccount, IEnumerable<KeyEdit> rows)
    {
        if (rowsFromAccount) return;
        foreach (var row in rows.Where(r => r.Dirty)) secrets.Set(row.Name, row.Removing ? null : row.Value);
        secrets.Save();
    }
}
