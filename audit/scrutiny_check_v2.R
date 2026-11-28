# Independent check of CONFIRM's flagged rows against the scrutiny R package.
#
# CONFIRM's own tests -- exhaustive enumeration and an inverse interval
# re-derivation -- are both its author's code, so neither is independent of it.
# scrutiny is a separate implementation by a separate author, and its GRIMMER
# follows Allard's Analytic-GRIMMER rather than CONFIRM's parity condition on
# the sum of squares.
#
# Written against scrutiny 1.0.0, which changed the interface: x and sd are
# numbers and the decimal count is passed explicitly as digits_x / digits_sd,
# replacing the old convention of quoting them as strings. items_averaged and
# data_type are now required too.
#
# The comparison is run under two rounding conventions, because the default is
# not the one CONFIRM uses and the difference would otherwise look like a bug:
#
#   up_or_down  scrutiny's default. A value is consistent if EITHER rounding
#               direction can produce it, so this is the more permissive test
#               and should flag no more than CONFIRM does.
#   up          half-up only, which is what CONFIRM implements. This is the
#               like-for-like comparison and the one to read first.
#
# Run from the repository root:
#   & "C:\Program Files\R\R-4.6.2\bin\Rscript.exe" audit/scrutiny_check_v2.R

user_lib <- Sys.getenv("R_LIBS_USER")
if (nzchar(user_lib)) .libPaths(c(user_lib, .libPaths()))
library(scrutiny)

path <- "audit/flagged_for_scrutiny.csv"
if (!file.exists(path)) stop("run from the repository root; ", path, " not found")
flagged <- read.csv(path, colClasses = "character")

# The decimal count has to come from the original text: 2.30 and 2.3 are
# different inputs to GRIM, and as.numeric() would lose the distinction.
decimals <- function(s) {
  s <- as.character(s)
  ifelse(grepl("\\.", s, fixed = FALSE), nchar(sub("^[^.]*\\.", "", s)), 0L)
}

cat("scrutiny version:", as.character(packageVersion("scrutiny")), "\n")
cat("rows to check:", nrow(flagged), "\n\n")

g <- flagged[flagged$test == "GRIM", ]
m <- flagged[flagged$test == "GRIMMER", ]

g_in <- data.frame(x = as.numeric(g$x), n = as.numeric(g$n),
                   digits_x = decimals(g$x))
m_in <- data.frame(x = as.numeric(m$x), sd = as.numeric(m$sd),
                   n = as.numeric(m$n),
                   digits_x = decimals(m$x), digits_sd = decimals(m$sd))

run_one <- function(label, rows, call_fn, mode) {
  out <- tryCatch(call_fn(mode), error = function(e) {
    cat("  ", label, "/", mode, "-> ERROR:", conditionMessage(e), "\n")
    NULL
  })
  if (is.null(out)) return(invisible(NULL))
  if (!"consistency" %in% names(out)) {
    cat("  columns returned:", paste(names(out), collapse = ", "), "\n")
    stop("no `consistency` column; the interface has changed again")
  }
  disagree <- which(out$consistency)
  cat(sprintf("  %-8s rounding=%-12s agrees on %d of %d, disagrees on %d\n",
              label, mode, sum(!out$consistency), nrow(out), length(disagree)))
  for (i in disagree) {
    cat(sprintf("        %-13s %-38s x=%s sd=%s n=%s\n",
                rows$pmcid[i], substr(rows$variable[i], 1, 38),
                rows$x[i], rows$sd[i], rows$n[i]))
  }
  out
}

cat(sprintf("== GRIM (%d rows)\n", nrow(g_in)))
grim_out <- list()
for (mode in c("up", "up_or_down")) {
  grim_out[[mode]] <- run_one("GRIM", g, function(md) {
    grim_map(g_in, items_averaged = 1, data_type = "integer", rounding = md)
  }, mode)
}

cat(sprintf("\n== GRIMMER (%d rows)\n", nrow(m_in)))
grimmer_out <- list()
for (mode in c("up", "up_or_down")) {
  grimmer_out[[mode]] <- run_one("GRIMMER", m, function(md) {
    grimmer_map(m_in, items_averaged = 1, data_type = "integer",
                sd_meaning = "sd_sample", rounding = md)
  }, mode)
}

cat("\n==========================================================\n")
cat("Read the rounding=up lines first: that is the convention CONFIRM\n")
cat("implements, so it is the like-for-like comparison. Disagreements\n")
cat("under up_or_down alone are a convention difference, not an error\n")
cat("in either implementation.\n")
cat("==========================================================\n")

if (!is.null(grim_out[["up"]]))
  write.csv(grim_out[["up"]], "audit/scrutiny_grim_out.csv", row.names = FALSE)
if (!is.null(grimmer_out[["up"]]))
  write.csv(grimmer_out[["up"]], "audit/scrutiny_grimmer_out.csv", row.names = FALSE)
cat("\nfull output (rounding=up) -> audit/scrutiny_grim_out.csv,",
    "audit/scrutiny_grimmer_out.csv\n")
