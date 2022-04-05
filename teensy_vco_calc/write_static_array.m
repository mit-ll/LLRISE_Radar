function write_static_array(fh,fmt,arr_type,arr_name,arr)
% Copyright (C) 2020 MASSACHUSETTS INSTITUTE OF TECHNOLOGY
% Pass this in?
vals_per_line=4;

fprintf(fh,'static const %s %s[] = {\n',arr_type,arr_name);

arr_length = length(arr);
line_count = ceil(arr_length/vals_per_line);
% Print all but last line
for ii = 1:(line_count-1)
    i0 = (ii-1)*vals_per_line + 1;
    i1 = i0 + vals_per_line - 1;
    %fprintf('%d %d\n', i0,i1);
    fprintf(fh,'    ');
    fprintf(fh,[fmt,','],arr(i0:i1));
    fprintf(fh,'\n');
end
% print last line
fprintf(fh,'    ');
i0 = (line_count-1)*vals_per_line + 1;
i1 = arr_length;
%fprintf('%d %d\n', i0,i1);
if i0<i1, fprintf(fh,[fmt,','],arr(i0:(i1-1)));, end
fprintf(fh,[fmt,'};\n'],arr(i1));

end

