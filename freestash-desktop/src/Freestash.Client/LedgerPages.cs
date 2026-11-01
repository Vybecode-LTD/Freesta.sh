namespace Freestash.Client;

/// <summary>Paging the ledger the way the web does (freestash/web/src/lib/ledgerPages.ts): a keyset cursor, newest first.</summary>
public static class LedgerPages
{
    /// <summary>Entries per page; the web's <c>LEDGER_PAGE</c> matches.</summary>
    public const int Size = 100;

    /// <summary>The cursor for the page after <paramref name="page"/>, or null when it was the last: the server sends a short page only at the end.</summary>
    public static string? NextCursor(IReadOnlyList<LedgerEntry> page, int limit = Size) =>
        page.Count < limit ? null : page[^1].Id;
}
